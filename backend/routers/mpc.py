"""
MPC优化路由
"""

from fastapi import APIRouter, HTTPException
from pathlib import Path
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
import numpy as np
import sys

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.model_manager import ModelManager

router = APIRouter()

# 使用全局模型管理器
from .models import get_model_manager


class MPCRequest(BaseModel):
    """MPC优化请求"""
    dynamics_model_name: str
    initial_state: Dict[str, float]
    horizon: int = 10
    control_bounds: Optional[Dict[str, Dict[str, float]]] = None
    targets: Optional[Dict[str, Any]] = None


@router.post("/optimize")
async def optimize_feeding_strategy(request: MPCRequest) -> Dict[str, Any]:
    """
    优化补料策略
    """
    model_manager = get_model_manager()
    try:
        # 获取动态模型
        dynamics_model = model_manager.get_model(request.dynamics_model_name)
        
        if not dynamics_model.is_trained:
            raise HTTPException(status_code=400, detail="动态模型尚未训练")
        
        # 导入MPC控制器
        from mpc.mpc_controller import MPCController
        
        # 创建MPC控制器
        mpc = MPCController(
            dynamics_model=dynamics_model.model,
            x_scaler=dynamics_model.x_scaler,
            state_cols=dynamics_model.state_names,
            input_cols=dynamics_model.input_names,
            horizon=request.horizon,
        )
        
        # 设置控制边界
        if request.control_bounds:
            for var, bounds in request.control_bounds.items():
                if var in mpc.control_bounds:
                    mpc.control_bounds[var] = (bounds.get("min", 0), bounds.get("max", 100))
        
        # 转换初始状态
        x0 = np.array([request.initial_state.get(name, 0.0) for name in dynamics_model.state_names])
        
        # 运行MPC优化
        state_traj, control_traj = mpc.run(x0)
        
        # 格式化结果
        state_trajectory = []
        for i, state in enumerate(state_traj):
            state_dict = {name: float(state[j]) for j, name in enumerate(dynamics_model.state_names)}
            state_dict["time_step"] = i
            state_trajectory.append(state_dict)
        
        control_trajectory = []
        control_names = [name for name in dynamics_model.input_names if name not in dynamics_model.state_names]
        for i, control in enumerate(control_traj):
            control_dict = {name: float(control[j]) for j, name in enumerate(control_names)}
            control_dict["time_step"] = i
            control_trajectory.append(control_dict)
        
        # 生成补料建议
        feeding_recommendations = []
        for i in range(len(control_trajectory)):
            rec = {
                "time_step": i,
                "time_hours": i * 24,  # 假设每步24小时
                "actions": control_trajectory[i],
            }
            feeding_recommendations.append(rec)
        
        return {
            "dynamics_model": request.dynamics_model_name,
            "horizon": request.horizon,
            "state_trajectory": state_trajectory,
            "control_trajectory": control_trajectory,
            "feeding_recommendations": feeding_recommendations,
        }
    
    except KeyError:
        raise HTTPException(status_code=404, detail=f"模型 '{request.dynamics_model_name}' 不存在")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/compare-strategies")
async def compare_mpc_strategies(
    dynamics_models: List[str],
    initial_state: Dict[str, float],
    horizon: int = 10,
) -> Dict[str, Any]:
    """
    比较不同模型的MPC策略
    """
    model_manager = get_model_manager()
    try:
        results = {}
        
        for model_name in dynamics_models:
            # 获取模型
            dynamics_model = model_manager.get_model(model_name)
            
            if not dynamics_model.is_trained:
                continue
            
            # 导入MPC控制器
            from mpc.mpc_controller import MPCController
            
            # 创建MPC控制器
            mpc = MPCController(
                dynamics_model=dynamics_model.model,
                x_scaler=dynamics_model.x_scaler,
                state_cols=dynamics_model.state_names,
                input_cols=dynamics_model.input_names,
                horizon=horizon,
            )
            
            # 转换初始状态
            x0 = np.array([initial_state.get(name, 0.0) for name in dynamics_model.state_names])
            
            # 运行MPC优化
            state_traj, control_traj = mpc.run(x0)
            
            # 保存结果
            results[model_name] = {
                "final_vcd": float(state_traj[-1][0]),  # 假设VCD是第一个状态
                "state_trajectory": state_traj.tolist(),
                "control_trajectory": control_traj.tolist(),
            }
        
        return {
            "models": dynamics_models,
            "horizon": horizon,
            "results": results,
        }
    
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/control-bounds")
async def get_default_control_bounds() -> Dict[str, Dict[str, float]]:
    """
    获取默认控制边界
    """
    return {
        "temp": {"min": 30.0, "max": 40.0, "default": 37.0},
        "pH": {"min": 6.5, "max": 7.5, "default": 7.0},
        "Feed_Glc": {"min": 0.0, "max": 10.0, "default": 0.0},
        "Feed_Gln": {"min": 0.0, "max": 10.0, "default": 0.0},
    }


@router.get("/targets")
async def get_default_targets() -> Dict[str, Any]:
    """
    获取默认优化目标
    """
    return {
        "VCD": {"weight": 1.0, "target": 40.0},
        "Glc": {"weight": 0.5, "min": 2.0, "max": 10.0},
        "Gln": {"weight": 0.5, "min": 1.0, "max": 10.0},
        "Amm": {"weight": 0.8, "max": 8.0},
        "Lac": {"weight": 0.3, "max": 15.0},
    }



