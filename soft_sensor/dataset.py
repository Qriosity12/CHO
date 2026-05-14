from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler


TARGET_COLUMNS = ["VCD", "Titer"]

# 可作为输入特征的候选列（存在才会使用）
BASE_FEATURE_COLUMNS = [
    "t_h",
    "Glc",
    "Gln",
    "Amm",
    "Lac",
    "DCD",
    "Lysed",
    "temp",
    "pH",
    "Stir",
    "DO",
    "BRvol",
]

# 推荐的列顺序（如果从原始 in silico CSV 转换）
STANDARD_ORDER = [
    "run_id",
    "t_s",
    "t_h",
    "VCD",
    "Glc",
    "Gln",
    "Amm",
    "Lac",
    "DCD",
    "Lysed",
    "Titer",
    "temp",
    "pH",
    "Stir",
    "DO",
    "BRvol",
]


@dataclass
class SoftSensorDataset:
    """
    软传感器数据集封装：
    - X: (N, F) 特征矩阵
    - Y: (N, T) 目标矩阵（多输出）
    - feature_names / target_names: 列名
    - scalers: 用于后续在线推理的标准化器
    """

    X_train: np.ndarray
    X_val: np.ndarray
    X_test: np.ndarray
    Y_train: np.ndarray
    Y_val: np.ndarray
    Y_test: np.ndarray
    feature_names: List[str]
    target_names: List[str]
    x_scaler: StandardScaler
    y_scaler: StandardScaler | None


def load_standard_csv(path: Path) -> pd.DataFrame:
    """
    读取标准格式 CSV，或直接从原始 in silico CSV 自动转换为标准格式。

    - 如果文件本身已经是标准格式（包含 run_id / t_h 等列），则直接读取。
    - 否则，自动按 insilico_fixed_A_test.csv 的结构解析前三行表头并转换。
    """
    # 先尝试用默认方式读取部分行，判断是否已经是标准格式
    df_head = pd.read_csv(path, nrows=5)
    if "run_id" in df_head.columns or "t_h" in df_head.columns:
        df = pd.read_csv(path)
        if "run_id" not in df.columns:
            if "run_idx" in df.columns:
                df = df.rename(columns={"run_idx": "run_id"})
            else:
                raise ValueError("标准 CSV 中缺少 run_id 列。")
        if "t_h" not in df.columns and "t_s" in df.columns:
            df["t_s"] = pd.to_numeric(df["t_s"], errors="coerce")
            df["t_h"] = df["t_s"] / 3600.0
        return df

    # 否则认为是原始 in silico 格式：前三行是多重表头
    df_raw = pd.read_csv(path, header=None)
    if len(df_raw) < 4:
        raise ValueError("原始 CSV 行数过少，无法解析多重表头。")

    header_group = list(df_raw.iloc[0])  # 第 0 行：group, X, W, Z...
    header_var = list(df_raw.iloc[1])  # 第 1 行：var, VCD:VCD, X:Glc, ...
    header_kind = list(df_raw.iloc[2])  # 第 2 行：run_idx, timestamps, ...

    data = df_raw.iloc[3:].reset_index(drop=True)

    new_cols: List[str] = []
    for idx, (grp_desc, var_desc, kind_desc) in enumerate(
        zip(header_group, header_var, header_kind)
    ):
        name = None

        # 1) 特殊处理 run_idx / timestamps（来自第 2 行）
        if isinstance(kind_desc, str):
            kind_desc = kind_desc.strip()
            if kind_desc == "run_idx":
                name = "run_id"
            elif kind_desc == "timestamps":
                name = "t_s"

        # 2) 其他列：从第 1 行 var_desc 里解析类似 "X:Glc" 的后半部分
        if name is None:
            if isinstance(var_desc, str):
                var_desc = var_desc.strip()
                if ":" in var_desc:
                    _, raw_name = var_desc.split(":", 1)
                else:
                    raw_name = var_desc
            else:
                raw_name = f"col_{idx}"

            raw_name = raw_name.strip()
            mapping = {
                "VCD": "VCD",
                "Glc": "Glc",
                "Gln": "Gln",
                "Amm": "Amm",
                "Lac": "Lac",
                "DCD": "DCD",
                "Lysed": "Lysed",
                "Titer": "Titer",
                "temp": "temp",
                "pH": "pH",
                "Stir": "Stir",
                "DO": "DO",
                "BRvol": "BRvol",
            }
            name = mapping.get(raw_name, raw_name)

        new_cols.append(name)

    data.columns = new_cols

    # 添加 t_h 派生列
    if "t_s" in data.columns and "t_h" not in data.columns:
        data["t_s"] = pd.to_numeric(data["t_s"], errors="coerce")
        data["t_h"] = data["t_s"] / 3600.0

    # 尽量按 STANDARD_ORDER 排列列顺序
    ordered = [c for c in STANDARD_ORDER if c in data.columns]
    others = [c for c in data.columns if c not in ordered]
    data = data[ordered + others]

    return data


def load_standard_csv_multi(paths: List[Path]) -> pd.DataFrame:
    """
    读取多个 CSV（标准或原始 in silico 格式），合并为一张表并统一重排 run_id。

    - 每个文件用 load_standard_csv 解析；
    - 按文件顺序对 run_id 做偏移，保证合并后不同文件的 run 不会重叠；
    - 列取并集，某文件中缺失的列在合并后为 NaN（后续按列存在性筛选特征/目标时会被忽略）。
    """
    if not paths:
        raise ValueError("paths 不能为空")
    dfs = []
    run_id_offset = 0
    for p in paths:
        path = Path(p)
        df = load_standard_csv(path)
        # 确保 run_id 为数值类型（部分 CSV 可能被读成字符串）
        df = df.copy()
        df["run_id"] = pd.to_numeric(df["run_id"], errors="coerce").fillna(0).astype(int)
        max_id = int(df["run_id"].max())
        df["run_id"] = df["run_id"] + run_id_offset
        run_id_offset += max_id + 1
        dfs.append(df)
    merged = pd.concat(dfs, axis=0, ignore_index=True, sort=False)
    return merged


def build_supervised_from_runs(
    df: pd.DataFrame,
    history_steps: int = 0,
    use_y_scaler: bool = True,
    test_run_frac: float = 0.2,
    val_frac_of_train: float = 0.2,
    random_state: int = 42,
) -> SoftSensorDataset:
    """
    将按 run_id 组织的时序数据，构造成监督学习样本。

    参数：
        history_steps: 使用多少个历史步作为输入（0 表示只用当前时刻）。
        use_y_scaler: 是否对输出做标准化。
        test_run_frac: 用多少比例的 run 作为测试集。
        val_frac_of_train: 在剩余的 train+val 中，再划出多少比例做 val。
    """
    df = df.copy()

    # 过滤掉目标列缺失的行
    available_targets = [c for c in TARGET_COLUMNS if c in df.columns]
    if not available_targets:
        raise ValueError(f"数据中不存在任何目标列: {TARGET_COLUMNS}")
    df = df.dropna(subset=available_targets)

    # 确定实际可用的特征列
    feature_cols = [c for c in BASE_FEATURE_COLUMNS if c in df.columns]
    if not feature_cols:
        raise ValueError(
            f"在数据中没有找到任何候选特征列: {BASE_FEATURE_COLUMNS}"
        )

    run_ids = sorted(df["run_id"].unique())

    # 按 run 抽样划分 train/val/test（避免时间泄漏）
    trainval_runs, test_runs = train_test_split(
        run_ids, test_size=test_run_frac, random_state=random_state
    )
    train_runs, val_runs = train_test_split(
        trainval_runs,
        test_size=val_frac_of_train,
        random_state=random_state,
    )

    def _make_samples_for_runs(selected_runs: List[int]) -> Tuple[np.ndarray, np.ndarray]:
        X_list: List[np.ndarray] = []
        Y_list: List[np.ndarray] = []

        for r in selected_runs:
            df_r = df[df["run_id"] == r].sort_values("t_h")
            # 简单按时间排序后构造时序窗口
            values_feat = df_r[feature_cols].values
            values_tgt = df_r[available_targets].values

            T = len(df_r)
            for t in range(T):
                # 至少要能取到当前时刻的特征
                if history_steps > 0:
                    if t - history_steps + 1 < 0:
                        continue
                    # 窗口 [t-history_steps+1, ..., t]
                    window = values_feat[t - history_steps + 1 : t + 1].reshape(
                        -1
                    )
                else:
                    window = values_feat[t]
                X_list.append(window)
                Y_list.append(values_tgt[t])

        if not X_list:
            raise ValueError("选定的 run_id 上没有构造出任何样本，请检查 history_steps 与数据长度。")

        X_arr = np.stack(X_list, axis=0)
        Y_arr = np.stack(Y_list, axis=0)
        return X_arr, Y_arr

    X_train_raw, Y_train_raw = _make_samples_for_runs(train_runs)
    X_val_raw, Y_val_raw = _make_samples_for_runs(val_runs)
    X_test_raw, Y_test_raw = _make_samples_for_runs(test_runs)

    # 标准化特征
    x_scaler = StandardScaler()
    X_train = x_scaler.fit_transform(X_train_raw)
    X_val = x_scaler.transform(X_val_raw)
    X_test = x_scaler.transform(X_test_raw)

    # 可选：标准化输出
    y_scaler: StandardScaler | None = None
    if use_y_scaler:
        y_scaler = StandardScaler()
        Y_train = y_scaler.fit_transform(Y_train_raw)
        Y_val = y_scaler.transform(Y_val_raw)
        Y_test = y_scaler.transform(Y_test_raw)
    else:
        Y_train, Y_val, Y_test = Y_train_raw, Y_val_raw, Y_test_raw

    return SoftSensorDataset(
        X_train=X_train,
        X_val=X_val,
        X_test=X_test,
        Y_train=Y_train,
        Y_val=Y_val,
        Y_test=Y_test,
        feature_names=_build_feature_names(feature_cols, history_steps),
        target_names=available_targets,
        x_scaler=x_scaler,
        y_scaler=y_scaler,
    )


def _build_feature_names(base_cols: List[str], history_steps: int) -> List[str]:
    if history_steps <= 0:
        return base_cols
    names: List[str] = []
    for h in range(history_steps):
        lag = history_steps - 1 - h
        suffix = f"(t-{lag})" if lag > 0 else "(t)"
        for c in base_cols:
            names.append(f"{c}_{suffix}")
    return names


def main_demo():
    """
    简单命令行演示：从标准 CSV 读取数据并打印数据集形状。
    用法示例：
        python -m soft_sensor.dataset data_processed/insilico_fixed_A_test_standard.csv
    """
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("csv", help="标准格式 CSV 路径（*_standard.csv）")
    parser.add_argument(
        "--history",
        type=int,
        default=0,
        help="作为输入使用的历史步数（0 表示只用当前时刻）",
    )
    args = parser.parse_args()

    csv_path = Path(args.csv)
    df_std = load_standard_csv(csv_path)
    ds = build_supervised_from_runs(df_std, history_steps=args.history)

    print("Feature shape (train):", ds.X_train.shape)
    print("Target shape (train):", ds.Y_train.shape)
    print("Features:", ds.feature_names)
    print("Targets:", ds.target_names)


if __name__ == "__main__":
    main_demo()

