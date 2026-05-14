"""
MPC 可信度加权补丁
这个模块提供了可信度加权的目标函数计算
"""
from typing import Dict, Tuple
import numpy as np


def compute_credibility_weighted_objective(
    trajectory: np.ndarray,
    state_columns: list,
    control_sequence: np.ndarray,
    config,
    credibility_weights: Dict[str, float],
    vcd_idx: int = None,
    titer_idx: int = None,
) -> float:
    """
    计算可信度加权的目标函数
    
    参数：
        trajectory: 预测状态轨迹 (H+1, n_states)
        state_columns: 状态变量名列表
        control_sequence: 控制序列 (H, n_controls)
        config: MPC配置
        credibility_weights: 各变量的可信度权重
        vcd_idx: VCD在状态向量中的索引
        titer_idx: Titer在状态向量中的索引
    
    返回：
        加权后的总代价
    """
    cost = 0.0
    
    # 1. VCD优化（根据可信度加权）
    if vcd_idx is not None:
        vcd_weight = credibility_weights.get('VCD', 1.0)
        vcd_trajectory = trajectory[:, vcd_idx]
        terminal_vcd = trajectory[-1, vcd_idx]
        
        if config.target_vcd is not None:
            cost += vcd_weight * config.weight_vcd * np.sum((vcd_trajectory - config.target_vcd) ** 2)
        else:
            cost -= vcd_weight * config.weight_vcd * terminal_vcd
            vcd_growth = terminal_vcd - trajectory[0, vcd_idx]
            cost -= vcd_weight * config.weight_vcd * 0.5 * vcd_growth
    
    # 2. Titer优化（根据可信度加权）
    if titer_idx is not None:
        titer_weight = credibility_weights.get('Titer', 1.0)
        terminal_titer = trajectory[-1, titer_idx]
        
        if config.target_titer is not None:
            cost += titer_weight * config.weight_titer * (terminal_titer - config.target_titer) ** 2
        else:
            cost -= titer_weight * config.weight_terminal * config.weight_titer * terminal_titer
    
    # 3. 营养物维持（根据可信度加权）
    if "Glc" in state_columns:
        glc_idx = state_columns.index("Glc")
        glc_weight = credibility_weights.get('Glc', 1.0)
        glc_trajectory = trajectory[:, glc_idx]
        
        glc_target = 4.0
        glc_tracking_error = np.sum((glc_trajectory - glc_target) ** 2)
        cost += glc_weight * 20.0 * glc_tracking_error
        
        glc_min_threshold = 2.0
        glc_penalty = np.sum(np.maximum(0, glc_min_threshold - glc_trajectory) ** 2)
        cost += glc_weight * 100.0 * glc_penalty
        
        if glc_trajectory[-1] < 1.0:
            cost += glc_weight * 200.0 * (1.0 - glc_trajectory[-1]) ** 2
    
    if "Gln" in state_columns:
        gln_idx = state_columns.index("Gln")
        gln_weight = credibility_weights.get('Gln', 1.0)
        gln_trajectory = trajectory[:, gln_idx]
        
        gln_target = 3.0
        gln_tracking_error = np.sum((gln_trajectory - gln_target) ** 2)
        cost += gln_weight * 20.0 * gln_tracking_error
        
        gln_min_threshold = 1.0
        gln_penalty = np.sum(np.maximum(0, gln_min_threshold - gln_trajectory) ** 2)
        cost += gln_weight * 100.0 * gln_penalty
        
        if gln_trajectory[-1] < 0.5:
            cost += gln_weight * 200.0 * (0.5 - gln_trajectory[-1]) ** 2
    
    # 4. 控制输入平滑性
    if control_sequence.shape[0] > 1:
        du = np.diff(control_sequence, axis=0)
        cost += config.weight_control * 0.01 * np.sum(du ** 2)
    
    return cost


def get_credibility_weights_from_config(config) -> Dict[str, float]:
    """从配置中提取可信度权重"""
    if not config.use_credibility or config.test_metrics is None:
        # 如果不使用可信度，返回全1权重
        return {var: 1.0 for var in config.test_metrics.keys()} if config.test_metrics else {}
    
    from mpc.credibility import CredibilityAssessor
    
    assessor = CredibilityAssessor(
        config.experimental_std or {},
        config.test_metrics or {}
    )
    return assessor.get_credibility_weights()

