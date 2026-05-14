"""
可信度评估和加权模块
用于MPC中根据模型预测精度调整优化权重
"""
from typing import Dict, Tuple
import numpy as np


class CredibilityAssessor:
    """
    可信度评估器
    
    根据RMSE和R²评估模型预测的可信度
    """
    
    def __init__(
        self,
        experimental_std: Dict[str, float],
        test_metrics: Dict[str, Dict[str, float]],
    ):
        """
        初始化可信度评估器
        
        参数：
            experimental_std: 实验标准差 {'VCD': 15.59, 'Glc': 6.72, ...}
            test_metrics: 测试集指标 {'VCD': {'rmse': 4.17, 'r2': 0.922}, ...}
        """
        self.experimental_std = experimental_std
        self.test_metrics = test_metrics
    
    def assess_credibility(self, var_name: str) -> Tuple[str, float]:
        """
        评估单个变量的可信度
        
        返回：
            (credibility_level, weight)
            - credibility_level: 'high', 'mid', 'low'
            - weight: 0.1 ~ 1.0
        
        判定标准（基于 R² 和 RMSE 的组合）：
            高: R² ≥ 0.85 且 RMSE ≤ 1.5σ
            中: (R² ≥ 0.70 且 RMSE ≤ 2.0σ) 或 (R² ≥ 0.80 且 RMSE ≤ 2.5σ)
            低: R² < 0.70 或 RMSE > 2.5σ
        """
        if var_name not in self.test_metrics:
            return 'unknown', 0.5
        
        metrics = self.test_metrics[var_name]
        rmse = metrics.get('rmse', float('inf'))
        r2 = metrics.get('r2', 0.0)
        
        sigma = self.experimental_std.get(var_name, float('inf'))
        
        # 高可信度：R² ≥ 0.85 且 RMSE ≤ 1.5σ
        if r2 >= 0.85 and rmse <= 1.5 * sigma:
            return 'high', 1.0
        
        # 中可信度：满足以下任一条件
        # 1. R² ≥ 0.70 且 RMSE ≤ 2.0σ
        # 2. R² ≥ 0.80 且 RMSE ≤ 2.5σ
        if (r2 >= 0.70 and rmse <= 2.0 * sigma) or (r2 >= 0.80 and rmse <= 2.5 * sigma):
            return 'mid', 0.6
        
        # 低可信度：R² < 0.70 或 RMSE > 2.5σ
        return 'low', 0.2
    
    def get_all_credibilities(self) -> Dict[str, Tuple[str, float]]:
        """获取所有变量的可信度"""
        credibilities = {}
        for var_name in self.test_metrics.keys():
            credibilities[var_name] = self.assess_credibility(var_name)
        return credibilities
    
    def get_credibility_weights(self) -> Dict[str, float]:
        """获取所有变量的权重"""
        weights = {}
        for var_name in self.test_metrics.keys():
            _, weight = self.assess_credibility(var_name)
            weights[var_name] = weight
        return weights


class CredibilityWeightedObjective:
    """
    可信度加权的目标函数
    
    根据各变量的可信度调整优化权重
    """
    
    def __init__(
        self,
        credibility_assessor: CredibilityAssessor,
        state_columns: list,
    ):
        self.assessor = credibility_assessor
        self.state_columns = state_columns
        self.weights = credibility_assessor.get_credibility_weights()
    
    def get_weight(self, var_name: str) -> float:
        """获取变量的权重"""
        return self.weights.get(var_name, 0.5)
    
    def apply_credibility_weighting(
        self,
        cost: float,
        var_name: str,
        credibility_level: str,
    ) -> float:
        """
        应用可信度加权
        
        参数：
            cost: 原始代价
            var_name: 变量名
            credibility_level: 可信度等级
        
        返回：
            加权后的代价
        
        权重调整策略：
            - 高可信度：权重 1.0，直接用于优化
            - 中可信度：权重 0.6，降低权重但仍参与优化
            - 低可信度：权重 0.2，最小化影响
        """
        weight = self.get_weight(var_name)
        
        if credibility_level == 'high':
            # 高可信度：直接用于优化
            return cost * weight
        elif credibility_level == 'mid':
            # 中可信度：降低权重，但仍用于优化
            return cost * weight * 0.8
        else:  # 'low'
            # 低可信度：最小化影响
            return cost * weight * 0.1
    
    def get_credibility_report(self) -> Dict[str, Dict]:
        """生成可信度报告"""
        report = {}
        for var_name in self.state_columns:
            level, weight = self.assessor.assess_credibility(var_name)
            metrics = self.assessor.test_metrics.get(var_name, {})
            sigma = self.assessor.experimental_std.get(var_name, 0)
            
            report[var_name] = {
                'credibility': level,
                'weight': weight,
                'rmse': metrics.get('rmse', 'N/A'),
                'r2': metrics.get('r2', 'N/A'),
                'sigma': sigma,
                'rmse_threshold_ok': metrics.get('rmse', float('inf')) <= sigma,
                'rmse_threshold_mid': metrics.get('rmse', float('inf')) <= 2 * sigma,
                'r2_threshold_high': metrics.get('r2', 0) > 0.9,
                'r2_threshold_mid': metrics.get('r2', 0) > 0.7,
            }
        return report


def print_credibility_report(report: Dict[str, Dict]) -> None:
    """打印可信度报告"""
    print("\n" + "="*80)
    print("模型可信度评估报告")
    print("="*80)
    print(f"{'变量':<10} {'可信度':<10} {'权重':<8} {'RMSE':<10} {'R²':<8} {'σ':<10}")
    print("-"*80)
    
    for var_name, info in report.items():
        credibility = info['credibility']
        weight = info['weight']
        rmse = f"{info['rmse']:.4f}" if isinstance(info['rmse'], float) else str(info['rmse'])
        r2 = f"{info['r2']:.3f}" if isinstance(info['r2'], float) else str(info['r2'])
        sigma = f"{info['sigma']:.2f}"
        
        print(f"{var_name:<10} {credibility:<10} {weight:<8.2f} {rmse:<10} {r2:<8} {sigma:<10}")
    
    print("="*80)
    print("可信度等级说明：")
    print("  ✓ 高 (high):   R² ≥ 0.85 且 RMSE ≤ 1.5σ  → 权重 1.0  → 直接用于优化")
    print("  △ 中 (mid):    (R² ≥ 0.70 且 RMSE ≤ 2.0σ) 或 (R² ≥ 0.80 且 RMSE ≤ 2.5σ)")
    print("                 → 权重 0.6  → 降低权重优化")
    print("  ⚠ 低 (low):    R² < 0.70 或 RMSE > 2.5σ  → 权重 0.2  → 仅用于约束")
    print("="*80 + "\n")

