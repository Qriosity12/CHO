"""
MPC控制器实现：基于软传感器和动态模型的补料策略优化
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List

import numpy as np
from scipy.optimize import minimize

from .blackbox_mpc import NextStateModel


@dataclass
class MPCConfig:
    """MPC控制器配置"""
    
    # 预测时域
    prediction_horizon: int = 10
    
    # 控制时域
    control_horizon: int = 5
    
    # 权重系数
    weight_vcd: float = 1.0  # VCD权重
    weight_titer: float = 10.0  # Titer权重（通常更重要）
    weight_control: float = 0.1  # 控制输入变化惩罚
    weight_terminal: float = 5.0  # 终端状态权重
    
    # 约束
    control_bounds: Dict[str, tuple[float, float]] | None = None  # 控制输入边界
    state_bounds: Dict[str, tuple[float, float]] | None = None  # 状态约束
    
    # 目标设定值
    target_vcd: float | None = None  # 目标VCD
    target_titer: float | None = None  # 目标Titer
    
    # 优化器设置
    optimizer_method: str = "SLSQP"  # 优化方法
    max_iterations: int = 100  # 最大迭代次数
    
    # 可信度配置（新增）
    use_credibility: bool = True  # 是否使用可信度加权
    credibility_scores: Dict[str, str] | None = None  # 各变量的可信度等级 {'VCD': 'high', 'Glc': 'high', ...}
    experimental_std: Dict[str, float] | None = None  # 实验标准差
    test_metrics: Dict[str, Dict[str, float]] | None = None  # 测试集指标 {'VCD': {'rmse': ..., 'r2': ...}, ...}
    
    # 总体可信度配置（新增）
    total_credibility_score: float | None = None  # 总体可信度分数 (0~1)
    total_credibility_level: str | None = None  # 总体可信度等级 ('high', 'mid', 'low')
    total_credibility_action: str | None = None  # 推荐动作 ('direct_use', 'limited_use', 'display_only')


class MPCController:
    """
    模型预测控制器（集成可信度加权）
    
    目标：最大化产物浓度（Titer）同时维持合理的细胞密度（VCD）
    
    可信度加权策略：
    - 高可信度（RMSE ≤ σ 且 R² > 0.9）：权重 = 1.0，直接用于优化
    - 中可信度（σ < RMSE ≤ 2σ 或 0.7 < R² ≤ 0.9）：权重 = 0.5，降低权重
    - 低可信度（RMSE > 2σ 或 R² ≤ 0.7）：权重 = 0.1，仅用于约束，不用于优化
    """
    
    def __init__(
        self,
        dynamics_model: NextStateModel,
        config: MPCConfig,
    ):
        self.model = dynamics_model
        self.config = config
        
        # 确定VCD和Titer在状态向量中的索引
        self.vcd_idx = None
        self.titer_idx = None
        
        if "VCD" in self.model.state_columns:
            self.vcd_idx = self.model.state_columns.index("VCD")
        if "Titer" in self.model.state_columns:
            self.titer_idx = self.model.state_columns.index("Titer")
        
        # 设置默认控制边界
        if self.config.control_bounds is None:
            self.config.control_bounds = self._default_control_bounds()
        
        # 计算可信度权重
        self.credibility_weights = self._compute_credibility_weights()
        
        # 根据总体可信度等级调整优化策略
        self._apply_total_credibility_adjustment()
    
    def _compute_credibility_weights(self) -> Dict[str, float]:
        """计算各变量的可信度权重"""
        if not self.config.use_credibility:
            # 如果不使用可信度，返回空字典
            return {}
        
        if self.config.test_metrics is None:
            # 如果没有测试指标，返回空字典
            return {}
        
        from mpc.credibility import CredibilityAssessor
        
        assessor = CredibilityAssessor(
            self.config.experimental_std or {},
            self.config.test_metrics or {}
        )
        return assessor.get_credibility_weights()
    
    def _apply_total_credibility_adjustment(self) -> None:
        """
        根据总体可信度等级调整 MPC 优化策略
        
        新增逻辑：
        - 当总分 low 时：进入保守模式，降低补料权重，增加控制平滑性惩罚
        - 当总分 mid 时：允许执行但限制补料变化率
        - 当总分 high 时：按正常 MPC 输出执行
        """
        if self.config.total_credibility_level is None:
            return
        
        level = self.config.total_credibility_level
        score = self.config.total_credibility_score or 0.5
        
        if level == 'low':
            # 保守模式：降低补料权重，增加平滑性约束
            print(f"[MPC] 总体可信度低 (score={score})，进入保守模式")
            # 降低 Titer 权重（不过度追求产物）
            self.config.weight_titer *= 0.5
            # 增加控制平滑性惩罚
            self.config.weight_control *= 2.0
            # 标记为仅展示模式
            self._conservative_mode = True
            
        elif level == 'mid':
            # 限幅模式：允许执行但限制变化
            print(f"[MPC] 总体可信度中等 (score={score})，进入限幅模式")
            # 适度降低权重
            self.config.weight_titer *= 0.8
            # 增加平滑性约束
            self.config.weight_control *= 1.5
            self._conservative_mode = False
            
        else:  # 'high'
            # 正常模式
            print(f"[MPC] 总体可信度高 (score={score})，正常执行")
            self._conservative_mode = False
    
    def _default_control_bounds(self) -> Dict[str, tuple[float, float]]:
        """设置默认控制边界"""
        bounds = {}
        for ctrl in self.model.control_columns:
            if ctrl == "temp":
                bounds[ctrl] = (35.0, 38.0)  # 温度范围 (°C)
            elif ctrl == "pH":
                bounds[ctrl] = (6.8, 7.4)  # pH范围
            elif ctrl == "DO":
                bounds[ctrl] = (20.0, 60.0)  # 溶氧范围 (%)
            elif ctrl == "Stir":
                bounds[ctrl] = (50.0, 300.0)  # 搅拌速度 (rpm)
            elif ctrl == "BRvol":
                bounds[ctrl] = (0.0, 10.0)  # 补料体积 (L)
            elif ctrl == "Feed_Glc" or ctrl.startswith("Feed_") and "Glc" in ctrl:
                bounds[ctrl] = (0.0, 50.0)  # 葡萄糖补料速率 (mM/h 或 g/L/h)
            elif ctrl == "Feed_Gln" or ctrl.startswith("Feed_") and "Gln" in ctrl:
                bounds[ctrl] = (0.0, 20.0)  # 谷氨酰胺补料速率 (mM/h)
            elif ctrl.startswith("Feed_"):
                bounds[ctrl] = (0.0, 10.0)  # 其他补料变量的默认范围
            else:
                bounds[ctrl] = (0.0, 100.0)  # 通用默认范围（避免无界）
        return bounds
    
    def _objective_function(
        self,
        u_flat: np.ndarray,
        x0: np.ndarray,
    ) -> float:
        """
        MPC目标函数
        
        目标：
        1. 最大化终端Titer（主要目标）
        2. 维持VCD在合理范围
        3. 最小化控制输入变化
        """
        # 重塑控制序列
        u_sequence = u_flat.reshape(self.config.control_horizon, self.model.n_controls)
        
        # 扩展控制序列到预测时域（最后的控制输入保持不变）
        if self.config.prediction_horizon > self.config.control_horizon:
            u_last = u_sequence[-1:].repeat(
                self.config.prediction_horizon - self.config.control_horizon, axis=0
            )
            u_full = np.vstack([u_sequence, u_last])
        else:
            u_full = u_sequence[:self.config.prediction_horizon]
        
        # 前向仿真
        x = x0.copy()
        trajectory = [x]
        
        for t in range(self.config.prediction_horizon):
            x = self.model.predict_next(x, u_full[t])
            trajectory.append(x)
        
        trajectory = np.array(trajectory)
        
        # 计算目标函数各项
        cost = 0.0
        
        # 1. 最大化VCD（细胞密度）- 主要目标
        if self.vcd_idx is not None:
            vcd_trajectory = trajectory[:, self.vcd_idx]
            terminal_vcd = trajectory[-1, self.vcd_idx]
            
            if self.config.target_vcd is not None:
                # 跟踪目标VCD
                cost += self.config.weight_vcd * np.sum((vcd_trajectory - self.config.target_vcd) ** 2)
            else:
                # 最大化终端VCD（负号表示最大化）
                cost -= self.config.weight_vcd * terminal_vcd
                
                # 同时鼓励整个轨迹的VCD增长
                vcd_growth = terminal_vcd - trajectory[0, self.vcd_idx]
                cost -= self.config.weight_vcd * 0.5 * vcd_growth
        
        # 2. Titer优化（如果存在）
        if self.titer_idx is not None:
            terminal_titer = trajectory[-1, self.titer_idx]
            if self.config.target_titer is not None:
                cost += self.config.weight_titer * (terminal_titer - self.config.target_titer) ** 2
            else:
                cost -= self.config.weight_terminal * self.config.weight_titer * terminal_titer
        
        # 3. 营养物维持在目标范围（关键改进！）
        if "Glc" in self.model.state_columns:
            glc_idx = self.model.state_columns.index("Glc")
            glc_trajectory = trajectory[:, glc_idx]
            
            # 目标：维持Glc在3-6 mM范围
            glc_target = 4.0
            glc_tracking_error = np.sum((glc_trajectory - glc_target) ** 2)
            cost += 20.0 * glc_tracking_error  # 跟踪误差
            
            # 强烈惩罚Glc低于阈值
            glc_min_threshold = 2.0
            glc_penalty = np.sum(np.maximum(0, glc_min_threshold - glc_trajectory) ** 2)
            cost += 100.0 * glc_penalty
            
            # 额外惩罚终端Glc过低
            if glc_trajectory[-1] < 1.0:
                cost += 200.0 * (1.0 - glc_trajectory[-1]) ** 2
        
        if "Gln" in self.model.state_columns:
            gln_idx = self.model.state_columns.index("Gln")
            gln_trajectory = trajectory[:, gln_idx]
            
            # 目标：维持Gln在2-5 mM范围
            gln_target = 3.0
            gln_tracking_error = np.sum((gln_trajectory - gln_target) ** 2)
            cost += 20.0 * gln_tracking_error  # 跟踪误差
            
            # 强烈惩罚Gln低于阈值
            gln_min_threshold = 1.0
            gln_penalty = np.sum(np.maximum(0, gln_min_threshold - gln_trajectory) ** 2)
            cost += 100.0 * gln_penalty
            
            # 额外惩罚终端Gln过低
            if gln_trajectory[-1] < 0.5:
                cost += 200.0 * (0.5 - gln_trajectory[-1]) ** 2
        
        # 4. 控制输入变化惩罚（平滑控制）- 降低权重以允许更大的控制变化
        if self.config.control_horizon > 1:
            du = np.diff(u_sequence, axis=0)
            cost += self.config.weight_control * 0.01 * np.sum(du ** 2)  # 进一步降低
        
        return cost
    
    def optimize(
        self,
        x0: np.ndarray,
        u_init: np.ndarray | None = None,
    ) -> tuple[np.ndarray, Dict[str, Any]]:
        """
        求解MPC优化问题
        
        参数：
            x0: 当前状态
            u_init: 初始控制序列猜测
        
        返回：
            u_opt: 最优控制序列
            info: 优化信息
        """
        # 初始化控制序列（自适应初始猜测）
        if u_init is None:
            u_init = np.zeros((self.config.control_horizon, self.model.n_controls))
            
            # 根据当前状态自适应设置初始猜测
            for i, ctrl_name in enumerate(self.model.control_columns):
                if "Feed_Glc" in ctrl_name:
                    # 根据当前Glc浓度调整初始猜测
                    if "Glc" in self.model.state_columns:
                        glc_idx = self.model.state_columns.index("Glc")
                        current_glc = x0[glc_idx]
                        # Glc越低，初始喂料越高
                        if current_glc < 1.0:
                            u_init[:, i] = 15.0
                        elif current_glc < 3.0:
                            u_init[:, i] = 10.0
                        elif current_glc < 5.0:
                            u_init[:, i] = 5.0
                        else:
                            u_init[:, i] = 2.0
                    else:
                        u_init[:, i] = 5.0
                        
                elif "Feed_Gln" in ctrl_name:
                    # 根据当前Gln浓度调整初始猜测
                    if "Gln" in self.model.state_columns:
                        gln_idx = self.model.state_columns.index("Gln")
                        current_gln = x0[gln_idx]
                        # Gln越低，初始喂料越高
                        if current_gln < 0.5:
                            u_init[:, i] = 10.0
                        elif current_gln < 2.0:
                            u_init[:, i] = 7.0
                        elif current_gln < 4.0:
                            u_init[:, i] = 5.0
                        else:
                            u_init[:, i] = 3.0
                    else:
                        u_init[:, i] = 3.0
                        
                elif ctrl_name == "temp":
                    u_init[:, i] = 35.0
                elif ctrl_name == "pH":
                    u_init[:, i] = 6.8
                elif ctrl_name == "Stir":
                    u_init[:, i] = 100.0
                elif ctrl_name == "DO":
                    u_init[:, i] = 40.0
        
        u_flat_init = u_init.flatten()
        
        # 构造边界约束
        bounds = []
        for t in range(self.config.control_horizon):
            for ctrl_name in self.model.control_columns:
                lb, ub = self.config.control_bounds.get(ctrl_name, (-np.inf, np.inf))
                bounds.append((lb, ub))
        
        # 求解优化问题
        result = minimize(
            fun=lambda u: self._objective_function(u, x0),
            x0=u_flat_init,
            method=self.config.optimizer_method,
            bounds=bounds,
            options={"maxiter": self.config.max_iterations, "disp": False},
        )
        
        # 提取最优控制序列
        u_opt = result.x.reshape(self.config.control_horizon, self.model.n_controls)
        
        info = {
            "success": result.success,
            "cost": result.fun,
            "iterations": result.nit if hasattr(result, "nit") else None,
            "message": result.message,
        }
        
        return u_opt, info
    
    def step(
        self,
        x0: np.ndarray,
        u_prev: np.ndarray | None = None,
    ) -> tuple[np.ndarray, Dict[str, Any]]:
        """
        执行一步MPC控制（滚动时域）
        
        参数：
            x0: 当前状态
            u_prev: 上一步的控制序列（用于warm start）
        
        返回：
            u_current: 当前时刻应用的控制输入
            info: 优化信息
        """
        # 构造初始猜测（使用上一步的控制序列进行warm start）
        if u_prev is not None and len(u_prev) >= self.config.control_horizon:
            # 将上一步的控制序列向前移动一步
            u_init = np.vstack([u_prev[1:self.config.control_horizon], u_prev[-1:]])
        else:
            u_init = None
        
        # 求解优化问题
        u_opt, info = self.optimize(x0, u_init)
        
        # 返回第一个控制输入（MPC的滚动时域策略）
        u_current = u_opt[0]
        
        # 保存完整序列供下次warm start
        info["u_sequence"] = u_opt
        
        return u_current, info


def simulate_mpc_closed_loop(
    controller: MPCController,
    x0: np.ndarray,
    steps: int,
    verbose: bool = True,
) -> tuple[np.ndarray, np.ndarray, List[Dict[str, Any]]]:
    """
    闭环MPC仿真
    
    参数：
        controller: MPC控制器
        x0: 初始状态
        steps: 仿真步数
        verbose: 是否打印详细信息
    
    返回：
        state_trajectory: 状态轨迹 (steps+1, n_states)
        control_trajectory: 控制轨迹 (steps, n_controls)
        info_list: 每步的优化信息
    """
    state_traj = [x0.copy()]
    control_traj = []
    info_list = []
    
    x = x0.copy()
    u_prev = None
    
    for t in range(steps):
        if verbose:
            print(f"\n=== 时刻 t={t} ===")
            print(f"当前状态: {x}")
        
        # 求解MPC
        u_current, info = controller.step(x, u_prev)
        
        if verbose:
            print(f"最优控制: {u_current}")
            print(f"优化成功: {info['success']}, 代价: {info['cost']:.4f}")
        
        # 应用控制并更新状态
        x = controller.model.predict_next(x, u_current)
        
        # 记录
        state_traj.append(x.copy())
        control_traj.append(u_current.copy())
        info_list.append(info)
        
        # 更新u_prev用于下次warm start
        u_prev = info.get("u_sequence")
    
    return (
        np.array(state_traj),
        np.array(control_traj),
        info_list,
    )


def main():
    """演示MPC控制器"""
    import argparse
    
    parser = argparse.ArgumentParser(description="MPC控制器演示")
    parser.add_argument(
        "--dynamics-dir",
        type=str,
        default="dynamics/artifacts",
        help="动态模型保存目录",
    )
    parser.add_argument(
        "--steps",
        type=int,
        default=20,
        help="仿真步数",
    )
    parser.add_argument(
        "--horizon",
        type=int,
        default=10,
        help="预测时域",
    )
    args = parser.parse_args()
    
    # 加载动态模型
    artifact_dir = Path(args.dynamics_dir)
    model = NextStateModel(
        model_path=artifact_dir / "next_state_model.joblib",
        scaler_path=artifact_dir / "x_scaler.joblib",
        state_columns_path=artifact_dir / "state_columns.txt",
        input_columns_path=artifact_dir / "input_columns.txt",
    )
    
    print("动态模型已加载")
    print(f"  状态变量: {model.state_columns}")
    print(f"  控制输入: {model.control_columns}")
    
    # 配置MPC
    config = MPCConfig(
        prediction_horizon=args.horizon,
        control_horizon=min(5, args.horizon),
        weight_titer=10.0,
        weight_vcd=1.0,
        weight_control=0.1,
    )
    
    controller = MPCController(model, config)
    
    # 初始状态（使用训练数据的均值）
    x0 = model.scaler.mean_[:model.n_states]
    
    print(f"\n开始MPC闭环仿真（{args.steps}步）...")
    state_traj, control_traj, info_list = simulate_mpc_closed_loop(
        controller, x0, args.steps, verbose=False
    )
    
    print("\n仿真完成！")
    print(f"状态轨迹形状: {state_traj.shape}")
    print(f"控制轨迹形状: {control_traj.shape}")
    
    # 显示关键指标
    if controller.vcd_idx is not None:
        vcd_init = state_traj[0, controller.vcd_idx]
        vcd_final = state_traj[-1, controller.vcd_idx]
        print(f"\nVCD: {vcd_init:.2f} -> {vcd_final:.2f}")
    
    if controller.titer_idx is not None:
        titer_init = state_traj[0, controller.titer_idx]
        titer_final = state_traj[-1, controller.titer_idx]
        print(f"Titer: {titer_init:.2f} -> {titer_final:.2f}")
        print(f"Titer增长: {((titer_final - titer_init) / (titer_init + 1e-8) * 100):.1f}%")


if __name__ == "__main__":
    main()

