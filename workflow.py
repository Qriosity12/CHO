"""
端到端Workflow：从数据到MPC补料策略
完整流程：数据预处理 -> 软传感器训练 -> 动态模型训练 -> MPC优化
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict

import numpy as np
import pandas as pd

from soft_sensor.dataset import load_standard_csv, load_standard_csv_multi, build_supervised_from_runs
from soft_sensor.train_soft_sensor import train_model as train_soft_sensor, evaluate as evaluate_soft_sensor
from soft_sensor.inference import load_predictor
from dynamics.train_next_state_model import build_next_step_dataset, train_next_state_model
from mpc.blackbox_mpc import NextStateModel
from mpc.mpc_controller import MPCController, MPCConfig, simulate_mpc_closed_loop


class WorkflowConfig:
    """Workflow配置"""
    
    def __init__(self, config_dict: Dict[str, Any] | None = None):
        if config_dict is None:
            config_dict = {}
        
        # 数据配置
        self.csv_files = config_dict.get("csv_files", [])
        self.output_dir = Path(config_dict.get("output_dir", "workflow_output"))
        
        # 软传感器配置
        self.soft_sensor_config = config_dict.get("soft_sensor", {})
        self.history_steps = self.soft_sensor_config.get("history_steps", 0)
        self.model_type = self.soft_sensor_config.get("model_type", "rf")
        self.target_columns = self.soft_sensor_config.get("target_columns", None)
        
        # 动态模型配置
        self.dynamics_config = config_dict.get("dynamics", {})
        self.include_controls = self.dynamics_config.get("include_controls", True)
        self.dynamics_model_type = self.dynamics_config.get("model_type", "rf")
        
        # MPC配置
        self.mpc_config = config_dict.get("mpc", {})
        self.prediction_horizon = self.mpc_config.get("prediction_horizon", 10)
        self.control_horizon = self.mpc_config.get("control_horizon", 5)
        self.simulation_steps = self.mpc_config.get("simulation_steps", 20)
        
        # 创建输出目录
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.soft_sensor_dir = self.output_dir / "soft_sensor"
        self.dynamics_dir = self.output_dir / "dynamics"
        self.mpc_dir = self.output_dir / "mpc"
        
        for d in [self.soft_sensor_dir, self.dynamics_dir, self.mpc_dir]:
            d.mkdir(exist_ok=True)


class CHOWorkflow:
    """CHO细胞培养优化完整工作流"""
    
    def __init__(self, config: WorkflowConfig):
        self.config = config
        self.results = {}
    
    def run(self, skip_training: bool = False) -> Dict[str, Any]:
        """
        运行完整workflow
        
        参数：
            skip_training: 是否跳过训练（使用已有模型）
        
        返回：
            results: 包含所有结果的字典
        """
        print("="*80)
        print("细胞培养优化Workflow")
        print("="*80)
        
        # 步骤1：加载数据
        print("\n[步骤 1/5] 加载和预处理数据...")
        df = self._load_data()
        self.results["data_shape"] = df.shape
        self.results["n_runs"] = df["run_id"].nunique()
        print(f"  数据形状: {df.shape}")
        print(f"  运行批次: {self.results['n_runs']}")
        
        if not skip_training:
            # 步骤2：训练软传感器
            print("\n[步骤 2/5] 训练软传感器...")
            soft_sensor_results = self._train_soft_sensor(df)
            self.results["soft_sensor"] = soft_sensor_results
            
            # 步骤3：训练动态模型
            print("\n[步骤 3/5] 训练动态模型...")
            dynamics_results = self._train_dynamics(df)
            self.results["dynamics"] = dynamics_results
        else:
            print("\n[跳过训练] 使用已有模型...")
        
        # 步骤4：配置MPC控制器
        print("\n[步骤 4/5] 配置MPC控制器...")
        controller = self._setup_mpc()
        
        # 步骤5：运行MPC仿真
        print("\n[步骤 5/5] 运行MPC闭环仿真...")
        mpc_results = self._run_mpc_simulation(controller)
        self.results["mpc"] = mpc_results
        
        # 保存结果
        self._save_results()
        
        print("\n" + "="*80)
        print("Workflow完成！")
        print("="*80)
        
        return self.results
    
    def _load_data(self) -> pd.DataFrame:
        """加载数据"""
        csv_paths = [Path(p) for p in self.config.csv_files]
        
        if len(csv_paths) == 1:
            df = load_standard_csv(csv_paths[0])
        else:
            df = load_standard_csv_multi(csv_paths)
        
        return df
    
    def _train_soft_sensor(self, df: pd.DataFrame) -> Dict[str, Any]:
        """训练软传感器"""
        import joblib
        
        # 构造数据集
        ds = build_supervised_from_runs(
            df,
            history_steps=self.config.history_steps,
            use_y_scaler=True,
        )
        
        print(f"  特征数量: {len(ds.feature_names)}")
        print(f"  目标变量: {', '.join(ds.target_names)}")
        print(f"  训练样本: {ds.X_train.shape[0]}")
        
        # 训练模型
        model = train_soft_sensor(ds, model_type=self.config.model_type)
        
        # 评估
        print("\n  训练集性能:")
        train_metrics = evaluate_soft_sensor(model, ds, split="train", return_metrics=True)
        print("\n  验证集性能:")
        val_metrics = evaluate_soft_sensor(model, ds, split="val", return_metrics=True)
        print("\n  测试集性能:")
        test_metrics = evaluate_soft_sensor(model, ds, split="test", return_metrics=True)
        
        # 保存模型
        model_path = self.config.soft_sensor_dir / f"soft_sensor_model_{self.config.model_type}.joblib"
        x_scaler_path = self.config.soft_sensor_dir / "x_scaler.joblib"
        y_scaler_path = self.config.soft_sensor_dir / "y_scaler.joblib"
        meta_path = self.config.soft_sensor_dir / "model_metadata.txt"
        
        joblib.dump(model, model_path)
        joblib.dump(ds.x_scaler, x_scaler_path)
        if ds.y_scaler is not None:
            joblib.dump(ds.y_scaler, y_scaler_path)
        
        with open(meta_path, "w", encoding="utf-8") as f:
            f.write(f"model_type: {self.config.model_type}\n")
            f.write(f"history_steps: {self.config.history_steps}\n")
            f.write(f"features: {','.join(ds.feature_names)}\n")
            f.write(f"targets: {','.join(ds.target_names)}\n")
        
        return {
            "model_path": str(model_path),
            "train_metrics": train_metrics,
            "val_metrics": val_metrics,
            "test_metrics": test_metrics,
            "feature_names": ds.feature_names,
            "target_names": ds.target_names,
        }
    
    def _train_dynamics(self, df: pd.DataFrame) -> Dict[str, Any]:
        """训练动态模型"""
        import joblib
        
        # 构造数据集
        (
            X_train, X_val, X_test,
            Y_train, Y_val, Y_test,
            state_cols, input_cols, x_scaler
        ) = build_next_step_dataset(
            df,
            include_controls=self.config.include_controls,
        )
        
        print(f"  状态变量: {state_cols}")
        print(f"  输入变量: {input_cols}")
        print(f"  训练样本: {X_train.shape[0]}")
        
        # 训练模型
        model = train_next_state_model(X_train, Y_train, model_type=self.config.dynamics_model_type)
        
        # 评估
        from dynamics.train_next_state_model import evaluate
        print("\n  训练集性能:")
        evaluate(model, X_train, Y_train, state_cols, split="train")
        print("\n  验证集性能:")
        evaluate(model, X_val, Y_val, state_cols, split="val")
        print("\n  测试集性能:")
        evaluate(model, X_test, Y_test, state_cols, split="test")
        
        # 保存模型
        model_path = self.config.dynamics_dir / f"next_state_model_{self.config.dynamics_model_type}.joblib"
        scaler_path = self.config.dynamics_dir / "x_scaler.joblib"
        state_meta_path = self.config.dynamics_dir / "state_columns.txt"
        input_meta_path = self.config.dynamics_dir / "input_columns.txt"
        
        joblib.dump(model, model_path)
        joblib.dump(x_scaler, scaler_path)
        state_meta_path.write_text("\n".join(state_cols), encoding="utf-8")
        input_meta_path.write_text("\n".join(input_cols), encoding="utf-8")
        
        return {
            "model_path": str(model_path),
            "state_columns": state_cols,
            "input_columns": input_cols,
        }
    
    def _setup_mpc(self) -> MPCController:
        """配置MPC控制器"""
        # 确定动态模型目录
        # 优先使用带模型类型后缀的目录（如dynamics_gp），因为它们是最新训练的
        dynamics_dir_with_type = self.config.output_dir / f"dynamics_{self.config.dynamics_model_type}"
        
        if dynamics_dir_with_type.exists():
            dynamics_dir = dynamics_dir_with_type
            model_filename = "next_state_model.joblib"
        else:
            dynamics_dir = self.config.dynamics_dir
            model_filename = f"next_state_model_{self.config.dynamics_model_type}.joblib"
            
            # 如果指定模型不存在，尝试使用默认模型
            if not (dynamics_dir / model_filename).exists():
                model_filename = "next_state_model.joblib"
        
        model_path = dynamics_dir / model_filename
        scaler_path = dynamics_dir / "x_scaler.joblib"
        state_columns_path = dynamics_dir / "state_columns.txt"
        input_columns_path = dynamics_dir / "input_columns.txt"
        
        # 检查文件是否存在
        if not model_path.exists():
            raise FileNotFoundError(
                f"未找到动态模型文件: {model_path}\n"
                f"请先运行训练或检查输出目录"
            )
        
        model = NextStateModel(
            model_path=model_path,
            scaler_path=scaler_path,
            state_columns_path=state_columns_path,
            input_columns_path=input_columns_path,
        )
        
        print(f"  加载模型: {model_path}")
        print(f"  状态变量: {model.state_columns}")
        print(f"  控制输入: {model.control_columns}")
        
        # 验证控制输入包含Feed_Glc和Feed_Gln
        if "Feed_Glc" not in model.control_columns or "Feed_Gln" not in model.control_columns:
            raise ValueError(
                f"动态模型缺少必需的控制输入！\n"
                f"期望: Feed_Glc, Feed_Gln, temp, pH\n"
                f"实际: {model.control_columns}\n"
                f"请使用 include_controls=True 重新训练动态模型"
            )
        
        # 配置MPC
        mpc_config = MPCConfig(
            prediction_horizon=self.config.prediction_horizon,
            control_horizon=self.config.control_horizon,
            weight_titer=self.config.mpc_config.get("weight_titer", 10.0),
            weight_vcd=self.config.mpc_config.get("weight_vcd", 1.0),
            weight_control=self.config.mpc_config.get("weight_control", 0.1),
        )
        
        controller = MPCController(model, mpc_config)
        
        return controller
    
    def _run_mpc_simulation(self, controller: MPCController) -> Dict[str, Any]:
        """运行MPC仿真"""
        # 初始状态（使用训练数据的均值）
        x0 = controller.model.scaler.mean_[:controller.model.n_states]
        
        print(f"  初始状态: {x0}")
        print(f"  仿真步数: {self.config.simulation_steps}")
        
        # 运行闭环仿真
        state_traj, control_traj, info_list = simulate_mpc_closed_loop(
            controller,
            x0,
            self.config.simulation_steps,
            verbose=False,
        )
        
        # 保存轨迹
        np.save(self.config.mpc_dir / "state_trajectory.npy", state_traj)
        np.save(self.config.mpc_dir / "control_trajectory.npy", control_traj)
        
        # 生成喂料建议表格
        self._generate_feeding_recommendations(
            state_traj, control_traj, controller
        )
        
        # 计算关键指标
        results = {
            "state_trajectory_shape": state_traj.shape,
            "control_trajectory_shape": control_traj.shape,
        }
        
        if controller.vcd_idx is not None:
            vcd_init = state_traj[0, controller.vcd_idx]
            vcd_final = state_traj[-1, controller.vcd_idx]
            results["vcd_initial"] = float(vcd_init)
            results["vcd_final"] = float(vcd_final)
            results["vcd_change"] = float(vcd_final - vcd_init)
            print(f"\n  VCD: {vcd_init:.2f} -> {vcd_final:.2f}")
        
        if controller.titer_idx is not None:
            titer_init = state_traj[0, controller.titer_idx]
            titer_final = state_traj[-1, controller.titer_idx]
            results["titer_initial"] = float(titer_init)
            results["titer_final"] = float(titer_final)
            results["titer_change"] = float(titer_final - titer_init)
            results["titer_improvement_pct"] = float((titer_final - titer_init) / (titer_init + 1e-8) * 100)
            print(f"  Titer: {titer_init:.2f} -> {titer_final:.2f}")
            print(f"  Titer改善: {results['titer_improvement_pct']:.1f}%")
        
        return results
    
    def _generate_feeding_recommendations(
        self, 
        state_traj: np.ndarray, 
        control_traj: np.ndarray,
        controller: MPCController
    ) -> None:
        """生成并保存喂料建议"""
        
        # 创建建议DataFrame
        recommendations = []
        state_cols = controller.model.state_columns
        control_cols = controller.model.control_columns
        
        for t in range(len(control_traj)):
            rec = {"时间步": t}
            
            # 添加状态预测
            for i, col in enumerate(state_cols):
                rec[f"预测_{col}"] = float(state_traj[t, i])
            
            # 添加控制建议
            for i, col in enumerate(control_cols):
                rec[f"建议_{col}"] = float(control_traj[t, i])
            
            recommendations.append(rec)
        
        df_rec = pd.DataFrame(recommendations)
        
        # 保存为CSV
        csv_path = self.config.mpc_dir / "feeding_recommendations.csv"
        df_rec.to_csv(csv_path, index=False, encoding="utf-8-sig")
        
        # 打印前几步建议
        print("\n" + "="*80)
        print("MPC喂料策略建议（前10步）")
        print("="*80)
        print(df_rec.head(10).to_string(index=False))
        print(f"\n完整建议已保存到: {csv_path}")
        
        # 生成人类可读的建议摘要
        summary_path = self.config.mpc_dir / "feeding_strategy_summary.txt"
        with open(summary_path, "w", encoding="utf-8") as f:
            f.write("="*80 + "\n")
            f.write("CHO细胞培养MPC优化喂料策略\n")
            f.write("="*80 + "\n\n")
            
            f.write("【控制目标】\n")
            f.write("- 最大化产物浓度（Titer）\n")
            f.write("- 维持细胞活力（VCD）\n")
            f.write("- 优化代谢物浓度（Glc, Gln, Amm, Lac）\n\n")
            
            f.write("【控制变量】\n")
            for col in control_cols:
                f.write(f"- {col}\n")
            f.write("\n")
            
            f.write("【关键建议】\n")
            for t in [0, 5, 10, 15, min(19, len(control_traj)-1)]:
                if t < len(control_traj):
                    f.write(f"\n时间步 {t}:\n")
                    for i, col in enumerate(control_cols):
                        f.write(f"  {col}: {control_traj[t, i]:.2f}\n")
                    
                    # 添加状态预测
                    f.write(f"  预测状态:\n")
                    for i, col in enumerate(state_cols):
                        f.write(f"    {col}: {state_traj[t, i]:.2f}\n")
            
            f.write("\n" + "="*80 + "\n")
            f.write("注：以上建议基于MPC优化算法，考虑了预测时域内的系统动态\n")
            f.write("建议根据实际生产情况和约束条件进行调整\n")
        
        print(f"策略摘要已保存到: {summary_path}")
    
    def _save_results(self) -> None:
        """保存结果摘要"""
        results_path = self.config.output_dir / "workflow_results.json"
        
        # 转换为可序列化格式
        serializable_results = {}
        for key, val in self.results.items():
            if isinstance(val, (dict, list, str, int, float, bool, type(None))):
                serializable_results[key] = val
            else:
                serializable_results[key] = str(val)
        
        with open(results_path, "w", encoding="utf-8") as f:
            json.dump(serializable_results, f, indent=2, ensure_ascii=False)
        
        print(f"\n结果已保存到: {results_path}")


def main():
    parser = argparse.ArgumentParser(
        description="CHO细胞培养优化端到端Workflow"
    )
    parser.add_argument(
        "csv",
        nargs="+",
        help="一个或多个CSV文件路径",
    )
    parser.add_argument(
        "-o", "--output-dir",
        type=str,
        default="workflow_output",
        help="输出目录",
    )
    parser.add_argument(
        "--config",
        type=str,
        help="配置文件路径（JSON格式）",
    )
    parser.add_argument(
        "--skip-training",
        action="store_true",
        help="跳过训练，使用已有模型",
    )
    parser.add_argument(
        "--model-type",
        type=str,
        default="rf",
        choices=["rf", "xgboost", "lightgbm", "mlp", "gp", "nn"],
        help="软传感器模型类型",
    )
    parser.add_argument(
        "--dynamics-model-type",
        type=str,
        default="rf",
        choices=["rf", "gp", "nn"],
        help="动态模型类型",
    )
    parser.add_argument(
        "--compare-models",
        action="store_true",
        help="对比多个动态模型的MPC策略",
    )
    parser.add_argument(
        "--compare-model-types",
        type=str,
        nargs="+",
        default=["rf", "gp", "nn"],
        choices=["rf", "gp", "nn"],
        help="要对比的动态模型类型（当--compare-models启用时）",
    )
    parser.add_argument(
        "--history",
        type=int,
        default=0,
        help="历史步数",
    )
    parser.add_argument(
        "--horizon",
        type=int,
        default=10,
        help="MPC预测时域",
    )
    parser.add_argument(
        "--steps",
        type=int,
        default=20,
        help="MPC仿真步数",
    )
    args = parser.parse_args()
    
    # 加载配置
    if args.config:
        with open(args.config, "r", encoding="utf-8") as f:
            config_dict = json.load(f)
    else:
        config_dict = {}
    
    # 命令行参数覆盖配置文件
    config_dict["csv_files"] = args.csv
    config_dict["output_dir"] = args.output_dir
    config_dict.setdefault("soft_sensor", {})["model_type"] = args.model_type
    config_dict.setdefault("soft_sensor", {})["history_steps"] = args.history
    config_dict.setdefault("dynamics", {})["model_type"] = args.dynamics_model_type
    config_dict.setdefault("mpc", {})["prediction_horizon"] = args.horizon
    config_dict.setdefault("mpc", {})["simulation_steps"] = args.steps
    
    # 如果启用模型对比
    if args.compare_models:
        print("\n" + "="*80)
        print("  多模型MPC策略对比模式")
        print("="*80)
        
        from compare_mpc_strategies import compare_multiple_models
        
        compare_multiple_models(
            csv_files=args.csv,
            model_types=args.compare_model_types,
            output_dir=args.output_dir,
            horizon=args.horizon,
            steps=args.steps,
            skip_training=args.skip_training,
        )
        
        print("\n[完成] 多模型对比完成！")
        print(f"[完成] 所有结果已保存到: {args.output_dir}")
        return
    
    # 创建workflow配置
    config = WorkflowConfig(config_dict)
    
    # 运行workflow
    workflow = CHOWorkflow(config)
    results = workflow.run(skip_training=args.skip_training)
    
    print("\n[完成] Workflow执行完成！")
    print(f"[完成] 所有结果已保存到: {config.output_dir}")


if __name__ == "__main__":
    main()

