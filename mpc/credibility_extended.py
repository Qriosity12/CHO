"""
扩展可信度评估模块
包含：变量级可信度、多步预测可信度、控制级可信度、总体可信度评分

设计目标：
1. 保留现有变量级可信度逻辑，增加 variable_score (0~1)
2. 新增多步预测可信度检查（基于开环验证或滚动预测）
3. 新增控制级可信度检查（基于MPC输出）
4. 生成统一的可信度总分，用于后端决策和前端展示
"""

from typing import Dict, Tuple, List, Optional, Any
import numpy as np
from dataclasses import dataclass


@dataclass
class VariableCredibilityInfo:
    """变量级可信度信息"""
    level: str  # 'high', 'mid', 'low'
    score: float  # 0~1
    weight: float  # MPC权重
    rmse: float
    r2: float
    sigma: float
    rmse_ratio: float  # RMSE / sigma
    r2_threshold_high: bool  # R² >= 0.85
    r2_threshold_mid: bool  # R² >= 0.70


@dataclass
class MultiStepCredibilityInfo:
    """多步预测可信度信息"""
    level: str  # 'high', 'mid', 'low'
    score: float  # 0~1
    rmse_1_step: float  # 一步预测RMSE
    rmse_3_step: float  # 三步预测RMSE
    rmse_horizon: float  # 整个预测时域平均RMSE
    horizon_error_growth: float  # 后期误差/前期误差
    decision_window_stability: float  # 关键窗口稳定性 (0~1)
    details: Dict[str, Any]  # 详细信息


@dataclass
class ControlCredibilityInfo:
    """控制级可信度信息"""
    level: str  # 'high', 'mid', 'low'
    score: float  # 0~1
    constraint_violation_risk: float  # 0~1，约束违反风险
    feed_change_rate: float  # 补料变化率 (0~1)
    strategy_stability: float  # 策略稳定性 (0~1)
    control_sensitivity: float  # 控制敏感性 (0~1)，暂时为placeholder
    details: Dict[str, Any]  # 详细信息


@dataclass
class TotalCredibilityInfo:
    """总体可信度信息"""
    level: str  # 'high', 'mid', 'low'
    score: float  # 0~1
    action: str  # 'direct_use', 'limited_use', 'display_only'
    reason: str  # 推荐理由
    variable_score: float
    multi_step_score: float
    control_score: float
    weights: Dict[str, float]  # 各部分权重


class VariableCredibilityAssessor:
    """
    变量级可信度评估器（改进版）
    
    基于RMSE、R²和实验标准差的组合判定
    """
    
    def __init__(
        self,
        experimental_std: Dict[str, float],
        test_metrics: Dict[str, Dict[str, float]],
    ):
        """
        初始化
        
        参数：
            experimental_std: 实验标准差 {'VCD': 15.59, 'Glc': 6.72, ...}
            test_metrics: 测试集指标 {'VCD': {'rmse': 4.17, 'r2': 0.922}, ...}
        """
        self.experimental_std = experimental_std
        self.test_metrics = test_metrics
    
    def assess_credibility(self, var_name: str) -> VariableCredibilityInfo:
        """
        评估单个变量的可信度
        
        判定标准（新版本）：
            高: R² ≥ 0.85 且 RMSE ≤ 1.5σ  → score=1.0, weight=1.0
            中: (R² ≥ 0.70 且 RMSE ≤ 2.0σ) 或 (R² ≥ 0.80 且 RMSE ≤ 2.5σ)  → score=0.6, weight=0.6
            低: R² < 0.70 或 RMSE > 2.5σ  → score=0.2, weight=0.2
        """
        if var_name not in self.test_metrics:
            return VariableCredibilityInfo(
                level='unknown', score=0.5, weight=0.5, rmse=0, r2=0, sigma=0,
                rmse_ratio=0, r2_threshold_high=False, r2_threshold_mid=False
            )
        
        metrics = self.test_metrics[var_name]
        rmse = metrics.get('rmse', float('inf'))
        r2 = metrics.get('r2', 0.0)
        sigma = self.experimental_std.get(var_name, float('inf'))
        
        rmse_ratio = rmse / sigma if sigma > 0 else float('inf')
        r2_high = r2 >= 0.85
        r2_mid = r2 >= 0.70
        
        # 判定等级
        if r2 >= 0.85 and rmse <= 1.5 * sigma:
            level = 'high'
            score = 1.0
            weight = 1.0
        elif (r2 >= 0.70 and rmse <= 2.0 * sigma) or (r2 >= 0.80 and rmse <= 2.5 * sigma):
            level = 'mid'
            score = 0.6
            weight = 0.6
        else:
            level = 'low'
            score = 0.2
            weight = 0.2
        
        return VariableCredibilityInfo(
            level=level,
            score=score,
            weight=weight,
            rmse=round(rmse, 4),
            r2=round(r2, 3),
            sigma=round(sigma, 4),
            rmse_ratio=round(rmse_ratio, 3),
            r2_threshold_high=r2_high,
            r2_threshold_mid=r2_mid
        )
    
    def get_all_credibilities(self) -> Dict[str, VariableCredibilityInfo]:
        """获取所有变量的可信度"""
        credibilities = {}
        for var_name in self.test_metrics.keys():
            credibilities[var_name] = self.assess_credibility(var_name)
        return credibilities
    
    def get_average_score(self) -> float:
        """获取所有变量的平均可信度分数"""
        credibilities = self.get_all_credibilities()
        if not credibilities:
            return 0.5
        scores = [info.score for info in credibilities.values()]
        return round(np.mean(scores), 3)


class MultiStepCredibilityAssessor:
    """
    多步预测可信度评估器
    
    基于开环验证结果或滚动预测结果，评估预测在多步时域内的稳定性
    """
    
    def __init__(
        self,
        state_columns: List[str],
        experimental_std: Dict[str, float],
        prediction_horizon: int = 10,
    ):
        """
        初始化
        
        参数：
            state_columns: 状态变量列表
            experimental_std: 实验标准差
            prediction_horizon: 预测时域长度
        """
        self.state_columns = state_columns
        self.experimental_std = experimental_std
        self.prediction_horizon = prediction_horizon
    
    def assess_from_open_loop_validation(
        self,
        open_loop_predictions: np.ndarray,  # shape (T, n_states)
        true_states: np.ndarray,  # shape (T, n_states)
    ) -> MultiStepCredibilityInfo:
        """
        基于开环验证结果评估多步预测可信度
        
        参数：
            open_loop_predictions: 开环预测状态轨迹
            true_states: 真实状态轨迹
        
        返回：
            MultiStepCredibilityInfo
        """
        T = min(len(open_loop_predictions), len(true_states))
        
        # 构建归一化向量：各变量除以各自的实验标准差 σ，消除量纲影响
        sigma_vec = np.array([
            self.experimental_std.get(col, 1.0) for col in self.state_columns
        ])
        sigma_vec = np.where(sigma_vec > 0, sigma_vec, 1.0)  # 防止除以0
        
        # 计算各步的归一化 RMSE
        step_rmses = []
        for t in range(T):
            pred = open_loop_predictions[t]
            true = true_states[t]
            # 归一化误差：(pred - true) / σ，再计算 RMSE
            norm_err = (pred - true) / sigma_vec
            rmse_t = float(np.sqrt(np.mean(norm_err ** 2)))
            step_rmses.append(rmse_t)
        
        step_rmses = np.array(step_rmses)
        
        # 提取关键指标
        # t=0 时预测值等于初始真实状态，误差必为0，跳过取 t=1 作为1步预测误差
        rmse_1_step = step_rmses[1] if len(step_rmses) > 1 else step_rmses[0]
        rmse_3_step = step_rmses[3] if len(step_rmses) > 3 else step_rmses[-1]
        # 平均RMSE 跳过 t=0
        rmse_horizon = np.mean(step_rmses[1:]) if len(step_rmses) > 1 else step_rmses[0]
        
        # 计算误差增长率
        if len(step_rmses) > 1:
            early_rmse = np.mean(step_rmses[:max(1, len(step_rmses)//3)])
            late_rmse = np.mean(step_rmses[max(1, 2*len(step_rmses)//3):])
            horizon_error_growth = late_rmse / (early_rmse + 1e-6)
        else:
            horizon_error_growth = 1.0
        
        # 计算关键窗口稳定性（跳过t=0，取第1步到中间段的预测误差）
        valid_rmses = step_rmses[1:] if len(step_rmses) > 1 else step_rmses
        mid_point = len(valid_rmses) // 2
        if mid_point > 0:
            early_rmses = valid_rmses[:mid_point]
            decision_window_stability = 1.0 - np.std(early_rmses) / (np.mean(early_rmses) + 1e-6)
            decision_window_stability = max(0, min(1, decision_window_stability))
        else:
            decision_window_stability = 0.5
        
        # 判定等级
        level, score = self._determine_level(
            rmse_1_step, rmse_3_step, rmse_horizon,
            horizon_error_growth, decision_window_stability
        )
        
        details = {
            'step_rmses': [round(x, 4) for x in step_rmses],
            'early_rmse': round(np.mean(valid_rmses[:mid_point]) if mid_point > 0 else 0, 4),
            'late_rmse': round(np.mean(valid_rmses[mid_point:]) if mid_point < len(valid_rmses) else 0, 4),
        }
        
        return MultiStepCredibilityInfo(
            level=level,
            score=score,
            rmse_1_step=round(rmse_1_step, 4),
            rmse_3_step=round(rmse_3_step, 4),
            rmse_horizon=round(rmse_horizon, 4),
            horizon_error_growth=round(horizon_error_growth, 3),
            decision_window_stability=round(decision_window_stability, 3),
            details=details
        )
    
    def _determine_level(
        self,
        rmse_1_step: float,
        rmse_3_step: float,
        rmse_horizon: float,
        horizon_error_growth: float,
        decision_window_stability: float,
    ) -> Tuple[str, float]:
        """
        根据多步预测指标判定可信度等级
        
        返回：
            (level, score)
        """
        # 计算综合分数
        # 1. 短期误差小 (0~1)
        # 归一化后 rmse_1_step 的含义是「误差占 σ 的比例」
        # rmse=0 完美，rmse=1 误差等于σ，rmse≥2 视为完全不可信
        short_term_score = 1.0 - min(1.0, rmse_1_step / 2.0)
        
        # 2. 误差增长平缓 (0~1)
        growth_score = 1.0 - min(1.0, (horizon_error_growth - 1.0) / 2.0)
        
        # 3. 关键窗口稳定 (0~1)
        stability_score = decision_window_stability
        
        # 综合分数
        score = 0.4 * short_term_score + 0.3 * growth_score + 0.3 * stability_score
        score = round(score, 3)
        
        # 判定等级
        if score >= 0.75:
            level = 'high'
        elif score >= 0.55:
            level = 'mid'
        else:
            level = 'low'
        
        return level, score


class ControlCredibilityAssessor:
    """
    控制级可信度评估器
    
    基于MPC输出结果评估控制策略的可靠性
    """
    
    def __init__(
        self,
        state_columns: List[str],
        control_columns: List[str],
        state_bounds: Optional[Dict[str, Tuple[float, float]]] = None,
        control_bounds: Optional[Dict[str, Tuple[float, float]]] = None,
    ):
        """
        初始化
        
        参数：
            state_columns: 状态变量列表
            control_columns: 控制变量列表
            state_bounds: 状态约束 {'VCD': (0, 100), ...}
            control_bounds: 控制约束 {'Feed_Glc': (0, 50), ...}
        """
        self.state_columns = state_columns
        self.control_columns = control_columns
        self.state_bounds = state_bounds or {}
        self.control_bounds = control_bounds or {}
    
    def assess_from_mpc_output(
        self,
        state_trajectory: np.ndarray,  # shape (T+1, n_states)
        control_trajectory: np.ndarray,  # shape (T, n_controls)
        previous_control: Optional[np.ndarray] = None,  # shape (n_controls,)
    ) -> ControlCredibilityInfo:
        """
        基于MPC输出评估控制级可信度
        
        参数：
            state_trajectory: 预测状态轨迹
            control_trajectory: 预测控制轨迹
            previous_control: 上一步的控制输入（用于计算变化率）
        
        返回：
            ControlCredibilityInfo
        """
        # 1. 计算约束违反风险
        constraint_violation_risk = self._compute_constraint_violation_risk(state_trajectory)
        
        # 2. 计算补料变化率
        feed_change_rate = self._compute_feed_change_rate(control_trajectory, previous_control)
        
        # 3. 计算策略稳定性
        strategy_stability = self._compute_strategy_stability(control_trajectory)
        
        # 4. 控制敏感性（暂时为placeholder）
        control_sensitivity = 0.5  # TODO: 后续可基于Jacobian或灵敏度分析实现
        
        # 判定等级
        level, score = self._determine_level(
            constraint_violation_risk,
            feed_change_rate,
            strategy_stability,
            control_sensitivity
        )
        
        details = {
            'constraint_violations': self._get_constraint_violation_details(state_trajectory),
            'max_feed_change': round(feed_change_rate, 3),
            'control_variance': round(np.var(control_trajectory, axis=0).mean(), 4) if len(control_trajectory) > 1 else 0,
        }
        
        return ControlCredibilityInfo(
            level=level,
            score=score,
            constraint_violation_risk=round(constraint_violation_risk, 3),
            feed_change_rate=round(feed_change_rate, 3),
            strategy_stability=round(strategy_stability, 3),
            control_sensitivity=round(control_sensitivity, 3),
            details=details
        )
    
    def _compute_constraint_violation_risk(self, state_trajectory: np.ndarray) -> float:
        """
        计算约束违反风险 (0~1)
        
        检查关键变量（Glc, Lac, Amm等）是否接近或超过约束边界
        """
        risk = 0.0
        
        # 定义关键变量的约束
        # Glc: 真正危险下限 0.5 g/L（耗竭）；2~3 g/L 为补料优先警戒区，上限 20 g/L
        # Lac: >40 mM 强风险；20 mM 为警戒线
        # Amm: >4 mM 强风险；2 mM 为警戒线
        # VCD: 不设实际上限，仅防负值
        critical_constraints = {
            'Glc': (0, 20.0),   # 低于 0.5 g/L 为耗竭硬边界；上限 20 g/L
            'Lac': (0.0, 40.0),   # >40 mM 强风险上限
            'Amm': (0.0, 4.0),    # >4 mM 强风险
            'VCD': (0.0, 1e9),    # 不设实际上限，仅防负值
        }
        
        # 警戒线（软边界，权重 0.5）
        warning_thresholds = {
            'Glc': {'low_warn': 2.0},   # 低于 2 g/L 进入补料优先区（警戒）
            'Lac': {'high_warn': 20.0}, # 超过 20 mM 进入警戒
            'Amm': {'high_warn': 2.0},  # 超过 2 mM 进入警戒
        }
        
        col_risks = {}
        for i, col in enumerate(self.state_columns):
            if col not in critical_constraints:
                continue
            
            lower, upper = critical_constraints[col]
            values = state_trajectory[:, i]
            
            # 计算硬边界违反比例（强风险）
            hard_violations = np.sum((values < lower) | (values > upper))
            violation_ratio = hard_violations / len(values)
            
            # 计算警戒线接近比例（中等风险，权重 0.5）
            near_ratio = 0.0
            if col in warning_thresholds:
                wt = warning_thresholds[col]
                if 'low_warn' in wt:
                    near_low = np.sum((values < wt['low_warn']) & (values >= lower))
                    near_ratio = max(near_ratio, near_low / len(values))
                if 'high_warn' in wt:
                    near_high = np.sum((values > wt['high_warn']) & (values <= upper))
                    near_ratio = max(near_ratio, near_high / len(values))
            
            # 单变量风险 = 违反比例 + 0.5 * 警戒比例
            col_risks[col] = min(1.0, violation_ratio + 0.5 * near_ratio)
        
        if not col_risks:
            return 0.0
        
        # 加权平均：Amm 和 Lac 权重更高（毒性更强）
        risk_weights = {'Glc': 1.0, 'Lac': 1.5, 'Amm': 2.0, 'VCD': 0.5}
        total_weight = sum(risk_weights.get(col, 1.0) for col in col_risks)
        risk = sum(col_risks[col] * risk_weights.get(col, 1.0) for col in col_risks) / total_weight
        
        return min(1.0, risk)
    
    def _compute_feed_change_rate(
        self,
        control_trajectory: np.ndarray,
        previous_control: Optional[np.ndarray] = None,
    ) -> float:
        """
        计算补料变化率 (0~1)
        
        衡量补料建议的变化幅度
        """
        if len(control_trajectory) < 2:
            return 0.0
        
        # 计算相邻时刻的控制变化
        control_diffs = np.diff(control_trajectory, axis=0)
        max_diff = np.max(np.abs(control_diffs))
        
        # 归一化：相对于控制范围
        control_range = 50.0  # 假设补料范围为0~50
        change_rate = min(1.0, max_diff / control_range)
        
        # 如果有上一步控制，也考虑第一步的变化
        if previous_control is not None:
            first_diff = np.max(np.abs(control_trajectory[0] - previous_control))
            first_change_rate = min(1.0, first_diff / control_range)
            change_rate = max(change_rate, first_change_rate)
        
        return change_rate
    
    def _compute_strategy_stability(self, control_trajectory: np.ndarray) -> float:
        """
        计算策略稳定性 (0~1)
        
        衡量控制序列是否平滑，避免剧烈振荡
        """
        if len(control_trajectory) < 3:
            return 0.8
        
        # 计算二阶差分（加速度）
        control_diffs = np.diff(control_trajectory, axis=0)
        control_accel = np.diff(control_diffs, axis=0)
        
        # 加速度越小，策略越稳定
        max_accel = np.max(np.abs(control_accel))
        
        # 归一化
        stability = 1.0 - min(1.0, max_accel / 10.0)
        
        return stability
    
    def _get_constraint_violation_details(self, state_trajectory: np.ndarray) -> Dict[str, Any]:
        """获取约束违反的详细信息"""
        details = {}
        
        critical_constraints = {
            'Glc': (0.5, 20.0),   # 低于 0.5 g/L 耗竭硬边界，上限 20 g/L
            'Lac': (0.0, 40.0),   # 上限 40 mM 强风险；20 mM 警戒
            'Amm': (0.0, 4.0),    # 上限 4 mM 强风险；2 mM 警戒
        }
        
        for i, col in enumerate(self.state_columns):
            if col not in critical_constraints:
                continue
            
            lower, upper = critical_constraints[col]
            values = state_trajectory[:, i]
            
            violations = np.sum((values < lower) | (values > upper))
            if violations > 0:
                details[col] = {
                    'violations': int(violations),
                    'min': round(float(np.min(values)), 3),
                    'max': round(float(np.max(values)), 3),
                    'bounds': (lower, upper)
                }
        
        return details
    
    def _determine_level(
        self,
        constraint_violation_risk: float,
        feed_change_rate: float,
        strategy_stability: float,
        control_sensitivity: float,
    ) -> Tuple[str, float]:
        """
        根据控制指标判定可信度等级
        
        返回：
            (level, score)
        """
        # 计算综合分数
        # 1. 约束风险低 (0~1)
        constraint_score = 1.0 - constraint_violation_risk
        
        # 2. 补料变化平缓 (0~1)
        change_score = 1.0 - feed_change_rate
        
        # 3. 策略稳定 (0~1)
        stability_score = strategy_stability
        
        # 综合分数
        score = 0.4 * constraint_score + 0.3 * change_score + 0.3 * stability_score
        score = round(score, 3)
        
        # 判定等级
        if score >= 0.75:
            level = 'high'
        elif score >= 0.55:
            level = 'mid'
        else:
            level = 'low'
        
        return level, score


class TotalCredibilityAssessor:
    """
    总体可信度评估器
    
    综合变量级、多步预测、控制级可信度，生成统一的总分和推荐动作
    """
    
    def __init__(
        self,
        variable_weight: float = 0.4,
        multi_step_weight: float = 0.3,
        control_weight: float = 0.3,
    ):
        """
        初始化
        
        参数：
            variable_weight: 变量级可信度权重
            multi_step_weight: 多步预测可信度权重
            control_weight: 控制级可信度权重
        """
        self.variable_weight = variable_weight
        self.multi_step_weight = multi_step_weight
        self.control_weight = control_weight
    
    def assess(
        self,
        variable_info: Dict[str, VariableCredibilityInfo],
        multi_step_info: MultiStepCredibilityInfo,
        control_info: ControlCredibilityInfo,
    ) -> TotalCredibilityInfo:
        """
        综合评估总体可信度
        
        参数：
            variable_info: 各变量的可信度信息
            multi_step_info: 多步预测可信度信息
            control_info: 控制级可信度信息
        
        返回：
            TotalCredibilityInfo
        """
        # 计算各部分的平均分数
        variable_score = np.mean([info.score for info in variable_info.values()]) if variable_info else 0.5
        multi_step_score = multi_step_info.score
        control_score = control_info.score
        
        # 计算总分
        total_score = (
            self.variable_weight * variable_score +
            self.multi_step_weight * multi_step_score +
            self.control_weight * control_score
        )
        total_score = round(total_score, 3)
        
        # 判定等级和推荐动作
        if total_score >= 0.80:
            level = 'high'
            action = 'direct_use'
            reason = '预测稳定且控制风险较低，可直接采用'
        elif total_score >= 0.60:
            level = 'mid'
            action = 'limited_use'
            reason = self._generate_mid_reason(variable_score, multi_step_score, control_score)
        else:
            level = 'low'
            action = 'display_only'
            reason = self._generate_low_reason(variable_score, multi_step_score, control_score)
        
        return TotalCredibilityInfo(
            level=level,
            score=total_score,
            action=action,
            reason=reason,
            variable_score=round(variable_score, 3),
            multi_step_score=round(multi_step_score, 3),
            control_score=round(control_score, 3),
            weights={
                'variable': self.variable_weight,
                'multi_step': self.multi_step_weight,
                'control': self.control_weight,
            }
        )
    
    def _generate_mid_reason(
        self,
        variable_score: float,
        multi_step_score: float,
        control_score: float,
    ) -> str:
        """生成中等可信度的推荐理由"""
        reasons = []
        
        if variable_score < 0.6:
            reasons.append('变量预测精度一般')
        if multi_step_score < 0.6:
            reasons.append('多步预测后段误差增长较快')
        if control_score < 0.6:
            reasons.append('控制策略存在一定风险')
        
        if not reasons:
            reasons.append('综合可信度中等')
        
        return '；'.join(reasons) + '，建议限幅采用'
    
    def _generate_low_reason(
        self,
        variable_score: float,
        multi_step_score: float,
        control_score: float,
    ) -> str:
        """生成低可信度的推荐理由"""
        reasons = []
        
        if variable_score < 0.4:
            reasons.append('变量预测精度较低')
        if multi_step_score < 0.4:
            reasons.append('多步预测明显发散')
        if control_score < 0.4:
            reasons.append('控制策略风险较高')
        
        if not reasons:
            reasons.append('综合可信度较低')
        
        return '；'.join(reasons) + '，建议仅作参考'


def generate_credibility_report(
    variable_info: Dict[str, VariableCredibilityInfo],
    multi_step_info: MultiStepCredibilityInfo,
    control_info: ControlCredibilityInfo,
    total_info: TotalCredibilityInfo,
) -> Dict[str, Any]:
    """
    生成完整的可信度报告
    
    返回：
        符合前端期望的数据结构
    """
    return {
        'variables': {
            var_name: {
                'level': info.level,
                'score': info.score,
                'weight': info.weight,
                'rmse': info.rmse,
                'r2': info.r2,
                'sigma': info.sigma,
                'rmse_ratio': info.rmse_ratio,
            }
            for var_name, info in variable_info.items()
        },
        'multi_step': {
            'level': multi_step_info.level,
            'score': multi_step_info.score,
            'rmse_1_step': multi_step_info.rmse_1_step,
            'rmse_3_step': multi_step_info.rmse_3_step,
            'rmse_horizon': multi_step_info.rmse_horizon,
            'horizon_error_growth': multi_step_info.horizon_error_growth,
            'decision_window_stability': multi_step_info.decision_window_stability,
        },
        'control': {
            'level': control_info.level,
            'score': control_info.score,
            'constraint_violation_risk': control_info.constraint_violation_risk,
            'feed_change_rate': control_info.feed_change_rate,
            'strategy_stability': control_info.strategy_stability,
        },
        'total': {
            'level': total_info.level,
            'score': total_info.score,
            'action': total_info.action,
            'reason': total_info.reason,
            'variable_score': total_info.variable_score,
            'multi_step_score': total_info.multi_step_score,
            'control_score': total_info.control_score,
        }
    }

