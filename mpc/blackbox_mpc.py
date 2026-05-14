from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List

import joblib
import numpy as np


@dataclass
class NextStateModel:
    """
    封装 x_{t+1} = f(x_t, u_t) 的黑盒模型，用于滚动预测。
    支持显式控制输入。
    """

    model_path: Path
    scaler_path: Path
    state_columns_path: Path
    input_columns_path: Path | None = None

    def __post_init__(self) -> None:
        self.model = joblib.load(self.model_path)
        self.scaler = joblib.load(self.scaler_path)
        
        cols_txt = self.state_columns_path.read_text(encoding="utf-8").strip()
        self.state_columns: List[str] = [c for c in cols_txt.splitlines() if c]

        # 加载输入列（状态+控制）
        if self.input_columns_path and self.input_columns_path.exists():
            input_txt = self.input_columns_path.read_text(encoding="utf-8").strip()
            self.input_columns: List[str] = [c for c in input_txt.splitlines() if c]
        else:
            # 向后兼容：如果没有input_columns，假设输入=状态
            self.input_columns = self.state_columns.copy()
        
        # 确定控制输入列
        self.control_columns: List[str] = [
            c for c in self.input_columns if c not in self.state_columns
        ]
        self.n_states = len(self.state_columns)
        self.n_controls = len(self.control_columns)

    def predict_next(self, x_t: np.ndarray, u_t: np.ndarray | None = None) -> np.ndarray:
        """
        预测下一状态
        
        参数：
            x_t: 当前状态，形状为 (n_states,)
            u_t: 控制输入，形状为 (n_controls,)，如果为None则从x_t中提取或使用零
        
        返回：
            x_{t+1}: 下一状态，形状为 (n_states,)
        """
        x_t = np.asarray(x_t, dtype=float).reshape(-1)
        
        # 构造完整输入 [x_t, u_t]
        if self.n_controls > 0:
            if u_t is None:
                # 如果没有提供控制输入，尝试从状态中提取或使用零
                u_t = np.zeros(self.n_controls)
            else:
                u_t = np.asarray(u_t, dtype=float).reshape(-1)
            
            input_vec = np.concatenate([x_t, u_t])
        else:
            input_vec = x_t
        
        input_vec = input_vec.reshape(1, -1)
        input_scaled = self.scaler.transform(input_vec)
        x_next = self.model.predict(input_scaled)
        return x_next.reshape(-1)


def simulate_open_loop(
    x0: np.ndarray,
    model: NextStateModel,
    steps: int,
    u_sequence: np.ndarray | None = None,
) -> np.ndarray:
    """
    使用训练好的 next-state 模型，从初始状态 x0 出发做开环滚动预测。
    
    参数：
        x0: 初始状态
        model: 动态模型
        steps: 预测步数
        u_sequence: 控制输入序列，形状为 (steps, n_controls)，如果为None则使用零控制
    
    返回：
        状态轨迹，形状为 (steps+1, n_states)
    """
    traj = [x0.reshape(-1)]
    x = x0.copy()
    
    for t in range(steps):
        if u_sequence is not None and model.n_controls > 0:
            u_t = u_sequence[t]
        else:
            u_t = None
        
        x = model.predict_next(x, u_t)
        traj.append(x)
    
    return np.stack(traj, axis=0)


def main():
    """
    简单演示：加载 dynamics/artifacts 下的模型，从某个初始状态做开环预测。
    用法示例：
        python -m mpc.blackbox_mpc
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="使用训练好的 next-state 模型做简单开环仿真（演示用）。"
    )
    parser.add_argument(
        "--artifact-dir",
        type=str,
        default="dynamics/artifacts",
        help="next-state 模型保存目录",
    )
    parser.add_argument(
        "--steps",
        type=int,
        default=10,
        help="从初始状态向前滚动预测的步数",
    )
    args = parser.parse_args()

    artifact_dir = Path(args.artifact_dir)
    model_path = artifact_dir / "next_state_model.joblib"
    scaler_path = artifact_dir / "x_scaler.joblib"
    state_cols_path = artifact_dir / "state_columns.txt"
    input_cols_path = artifact_dir / "input_columns.txt"

    if not model_path.exists():
        raise FileNotFoundError(
            f"未找到动态模型文件: {model_path}，请先运行 dynamics/train_next_state_model.py"
        )

    ns_model = NextStateModel(
        model_path=model_path,
        scaler_path=scaler_path,
        state_columns_path=state_cols_path,
        input_columns_path=input_cols_path if input_cols_path.exists() else None,
    )

    print(f"动态模型已加载")
    print(f"  状态变量: {ns_model.state_columns}")
    print(f"  控制输入: {ns_model.control_columns}")

    # 简单取一个"名义初始状态"（比如训练集中状态均值）
    # 这里直接从 scaler 中读取均值向量作为演示
    x0 = ns_model.scaler.mean_[:ns_model.n_states]
    
    # 使用零控制输入
    u_sequence = None
    if ns_model.n_controls > 0:
        u_sequence = np.zeros((args.steps, ns_model.n_controls))
    
    traj = simulate_open_loop(x0, ns_model, steps=args.steps, u_sequence=u_sequence)

    print("\n开环仿真结果：")
    print("State columns:", ns_model.state_columns)
    print("Trajectory shape:", traj.shape)
    print("\nFirst 3 steps of trajectory:")
    for i in range(min(3, traj.shape[0])):
        print(f"t+{i}: {traj[i]}")


if __name__ == "__main__":
    main()
