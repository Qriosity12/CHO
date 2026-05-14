"""
FastAPI后端服务器 - 简化版本
不依赖workflow.py，直接使用现有模块
"""
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.encoders import jsonable_encoder
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from pathlib import Path
from typing import Dict, Any, List, Optional
import os
import shutil
import json
import threading
import uuid
import asyncio
import pandas as pd
import numpy as np
from datetime import datetime
import math
import sys

app = FastAPI(title="CHO细胞培养优化系统")

# CORS配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 全局配置
BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIST_DIR = BASE_DIR / "frontend" / "dist"
UPLOAD_DIR = BASE_DIR / "api" / "uploads"
WORKSPACE_DIR = BASE_DIR / "api" / "workspace"
RESULTS_DIR = BASE_DIR / "api" / "results"
WORKFLOW_OUTPUT_DIR = BASE_DIR / "api" / "workflow_output"

for d in [UPLOAD_DIR, WORKSPACE_DIR, RESULTS_DIR, WORKFLOW_OUTPUT_DIR]:
    d.mkdir(parents=True, exist_ok=True)

if FRONTEND_DIST_DIR.exists():
    assets_dir = FRONTEND_DIST_DIR / "assets"
    images_dir = FRONTEND_DIST_DIR / "images"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")
    if images_dir.exists():
        app.mount("/images", StaticFiles(directory=images_dir), name="images")

# 会话级训练状态：仅在当前后端进程内，成功训练后置为 True
TRAINED_IN_SESSION = False
LAST_TRAIN_RESULT_FILE = None
PREDICT_MODEL_CACHE = {
    "dynamics_dir": None,
    "model": None,
    "scaler": None,
    "state_cols": None,
    "input_cols": None,
}
TRAINING_JOBS: Dict[str, Dict[str, Any]] = {}
TRAINING_JOBS_LOCK = threading.Lock()


def _set_training_job(job_id: str, **updates):
    with TRAINING_JOBS_LOCK:
        job = TRAINING_JOBS.setdefault(job_id, {"job_id": job_id})
        job.update(updates)
        return dict(job)


def _get_training_job(job_id: str) -> Optional[Dict[str, Any]]:
    with TRAINING_JOBS_LOCK:
        job = TRAINING_JOBS.get(job_id)
        return dict(job) if job else None


# ==================== 数据模型 ====================

class ModelConfig(BaseModel):
    """模型配置"""
    soft_sensor_model_type: str = "rf"
    dynamics_model_type: str = "rf"
    history_steps: int = 0
    include_controls: bool = True


class MPCConfig(BaseModel):
    """MPC配置"""
    prediction_horizon: int = 10
    control_horizon: int = 5
    simulation_steps: int = 20
    weight_titer: float = 10.0
    weight_vcd: float = 1.0
    weight_control: float = 0.1


class TrainRequest(BaseModel):
    """训练请求"""
    dataset_name: str
    model_settings: ModelConfig
    mpc_settings: MPCConfig


# ==================== API端点 ====================

@app.get("/")
async def root():
    """健康检查或返回前端首页"""
    index_file = FRONTEND_DIST_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {
        "status": "ok",
        "message": "CHO细胞培养优化系统API",
        "version": "1.0.0"
    }


@app.post("/api/upload")
async def upload_dataset(file: UploadFile = File(...)):
    """上传数据集"""
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{file.filename}"
        file_path = UPLOAD_DIR / filename
        
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # 读取CSV，跳过第一行（变量类型行）
        # 先读取前几行检查格式
        with open(file_path, 'r') as f:
            first_lines = [f.readline().strip() for _ in range(3)]
        
        # 检查是否是in silico格式（第3行包含run_idx）
        if len(first_lines) >= 3 and 'run_idx' in first_lines[2]:
            print("检测到in silico格式")
            # 读取第2行作为列名（var行）
            var_line = first_lines[1].split(',')
            
            # 处理前两列：第一列是空的对应run_idx，第二列是空的对应timestamps
            var_line[0] = 'run_idx'
            var_line[1] = 'timestamps'
            
            # 跳过前3行，使用var行作为列名
            df = pd.read_csv(file_path, skiprows=3, names=var_line)
            
            # 智能清理列名，保留关键信息避免重复
            rename_map = {}
            seen_names = {}  # 跟踪已使用的列名
            
            for col in df.columns:
                if isinstance(col, str):
                    new_name = col
                    
                    # 特殊处理：保留BolusFeed前缀
                    if 'BolusFeed' in col:
                        # BolusFeed:BRvol -> Feed_BRvol
                        # BolusFeed_Glc:Glc -> Feed_Glc
                        if ':' in col:
                            parts = col.split(':')
                            if 'BolusFeed_' in parts[0]:
                                # BolusFeed_Glc -> Feed_Glc
                                new_name = parts[0].replace('BolusFeed_', 'Feed_')
                            else:
                                # BolusFeed:BRvol -> Feed_BRvol
                                new_name = 'Feed_' + parts[-1]
                        else:
                            new_name = col.replace('BolusFeed', 'Feed')
                    
                    # 跳过Cumulative和SampleVol相关列（这些是累积量，不需要）
                    elif 'Cumulative' in col or 'SampleVol' in col or 'Volume:' in col or 'ComputedBRvol' in col:
                        new_name = None  # 标记为删除
                    
                    # 处理状态变量（X:Glc -> Glc）
                    elif ':' in col:
                        new_name = col.split(':')[-1]
                    
                    # 重命名run_idx和timestamps
                    elif col == 'run_idx':
                        new_name = 'run_id'
                    elif col == 'timestamps':
                        new_name = 't_h'
                    
                    # 处理重复列名
                    if new_name and new_name in seen_names:
                        # 如果重复，标记为删除（保留第一个）
                        new_name = None
                    
                    if new_name:
                        rename_map[col] = new_name
                        seen_names[new_name] = True
            
            # 删除不需要的列
            cols_to_drop = [col for col in df.columns if col not in rename_map]
            if cols_to_drop:
                df = df.drop(columns=cols_to_drop)
            
            # 重命名列
            if rename_map:
                df = df.rename(columns=rename_map)
            
            # 转换时间戳为小时
            if "t_h" in df.columns:
                df["t_h"] = pd.to_numeric(df["t_h"], errors='coerce')
                if df["t_h"].max() > 1000:
                    df["t_h"] = df["t_h"] / 3600
            
            # 确保run_id是数值类型
            if "run_id" in df.columns:
                df["run_id"] = pd.to_numeric(df["run_id"], errors='coerce')
            
            # 保存转换后的文件
            df.to_csv(file_path, index=False)
            print(f"已转换，列数: {len(df.columns)}, 列名: {list(df.columns)}")
        else:
            # 标准格式
            df = pd.read_csv(file_path)
        
        # 检查必需的列
        required_cols = ["run_id", "t_h"]
        missing_cols = [col for col in required_cols if col not in df.columns]
        
        if missing_cols:
            file_path.unlink()
            raise HTTPException(
                status_code=400,
                detail=f"数据集缺少必需的列: {missing_cols}。当前列: {list(df.columns)[:10]}"
            )
        
        return {
            "success": True,
            "filename": filename,
            "dataset_name": filename,
            "rows": len(df),
            "columns": list(df.columns),
            "runs": int(df["run_id"].nunique()),
            "message": "数据集上传成功"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        error_detail = f"上传失败: {str(e)}\n{traceback.format_exc()}"
        print(error_detail)
        raise HTTPException(status_code=400, detail=error_detail)


@app.get("/api/datasets")
async def list_datasets():
    """列出所有已上传的数据集"""
    try:
        datasets = []
        skipped_files = []

        for file_path in UPLOAD_DIR.glob("*.csv"):
            try:
                df = pd.read_csv(file_path)

                if "run_id" not in df.columns:
                    skipped_files.append({
                        "name": file_path.name,
                        "reason": "缺少 run_id 列"
                    })
                    continue

                datasets.append({
                    "name": file_path.name,
                    "size": file_path.stat().st_size,
                    "rows": len(df),
                    "runs": int(df["run_id"].nunique()),
                    "upload_time": datetime.fromtimestamp(file_path.stat().st_mtime).isoformat()
                })
            except Exception as file_error:
                skipped_files.append({
                    "name": file_path.name,
                    "reason": str(file_error)
                })
                continue

        return {
            "success": True,
            "datasets": datasets,
            "count": len(datasets),
            "skipped_files": skipped_files
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/train")
async def train_models(request: TrainRequest):
    """
    训练完整流程
    跳过软传感器，直接训练动态模型和MPC
    """
    global TRAINED_IN_SESSION, LAST_TRAIN_RESULT_FILE
    try:
        dataset_path = UPLOAD_DIR / request.dataset_name
        if not dataset_path.exists():
            raise HTTPException(status_code=404, detail=f"数据集不存在: {request.dataset_name}")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        from soft_sensor.dataset import load_standard_csv
        from sklearn.ensemble import RandomForestRegressor
        from sklearn.model_selection import train_test_split
        from sklearn.preprocessing import StandardScaler
        from sklearn.metrics import mean_squared_error, r2_score
        from mpc.blackbox_mpc import NextStateModel
        from mpc.mpc_controller import MPCController, MPCConfig, simulate_mpc_closed_loop
        import joblib

        print("=" * 80)
        print("开始训练流程")
        print("=" * 80)

        print("\n[步骤 1/3] 加载数据...")
        df = load_standard_csv(dataset_path)
        print(f"  数据形状: {df.shape}")
        print(f"  运行批次: {df['run_id'].nunique()}")
        
        # 步骤2：训练动态模型
        print("\n[步骤 2/3] 训练动态模型...")
        dynamics_dir = WORKFLOW_OUTPUT_DIR / f"dynamics_{request.model_settings.dynamics_model_type}"
        dynamics_dir.mkdir(parents=True, exist_ok=True)
        
        # 构建动态模型数据集
        STATE_COLUMNS = ["VCD", "Glc", "Gln", "Amm", "Lac", "Titer", "DCD", "Lysed"]
        CONTROL_COLUMNS = ["Feed_Glc", "Feed_Gln", "Feed_BRvol", "temp", "pH", "DO", "Stir"]
        
        state_cols = [c for c in STATE_COLUMNS if c in df.columns]
        control_cols = [c for c in CONTROL_COLUMNS if c in df.columns] if request.model_settings.include_controls else []
        control_cols = [c for c in control_cols if c not in state_cols]
        input_cols = state_cols + control_cols
        
        # 确保至少有一个控制变量
        if len(control_cols) == 0:
            print("  警告：没有找到控制变量，将使用状态变量作为输入")
            input_cols = state_cols
        
        print(f"  状态变量: {state_cols}")
        print(f"  输入变量: {input_cols}")
        
        # 构造next-step数据集
        run_ids = sorted(df["run_id"].unique())
        trainval_runs, test_runs = train_test_split(run_ids, test_size=0.2, random_state=42)
        train_runs, val_runs = train_test_split(trainval_runs, test_size=0.2, random_state=42)
        
        def make_pairs(selected_runs):
            X_list, Y_list = [], []
            for r in selected_runs:
                df_r = df[df["run_id"] == r].sort_values("t_h")
                state_values = df_r[state_cols].values
                input_values = df_r[input_cols].values
                T = len(df_r)
                for t in range(T - 1):
                    X_list.append(input_values[t])
                    Y_list.append(state_values[t + 1])
            return np.stack(X_list, axis=0), np.stack(Y_list, axis=0)
        
        X_train_raw, Y_train = make_pairs(train_runs)
        X_val_raw, Y_val = make_pairs(val_runs)
        X_test_raw, Y_test = make_pairs(test_runs)
        
        # 标准化
        x_scaler = StandardScaler()
        X_train = x_scaler.fit_transform(X_train_raw)
        X_val = x_scaler.transform(X_val_raw)
        X_test = x_scaler.transform(X_test_raw)
        
        print(f"  训练样本: {X_train.shape[0]}")
        
        # 训练模型
        if request.model_settings.dynamics_model_type == "rf":
            model = RandomForestRegressor(
                n_estimators=500,
                max_depth=20,
                min_samples_split=10,
                min_samples_leaf=5,
                max_features='sqrt',
                random_state=42,
                n_jobs=-1
            )
        else:
            model = RandomForestRegressor(n_estimators=100, random_state=42, n_jobs=-1)
        
        model.fit(X_train, Y_train)
        
        # 评估
        def evaluate_model(X, Y, split_name):
            Y_pred = model.predict(X)
            rmse = np.sqrt(mean_squared_error(Y, Y_pred, multioutput='raw_values'))
            r2 = r2_score(Y, Y_pred, multioutput='raw_values')
            print(f"\n  {split_name}性能:")
            metrics = {}
            for i, name in enumerate(state_cols):
                print(f"    {name}: RMSE={rmse[i]:.4f}, R2={r2[i]:.3f}")
                metrics[name] = {"rmse": round(float(rmse[i]), 4), "r2": round(float(r2[i]), 3)}
            return metrics
        
        train_metrics = evaluate_model(X_train, Y_train, "训练集")
        val_metrics = evaluate_model(X_val, Y_val, "验证集")
        test_metrics = evaluate_model(X_test, Y_test, "测试集")
        
        # 保存动态模型
        model_path = dynamics_dir / "next_state_model.joblib"
        scaler_path = dynamics_dir / "x_scaler.joblib"
        state_meta_path = dynamics_dir / "state_columns.txt"
        input_meta_path = dynamics_dir / "input_columns.txt"
        
        joblib.dump(model, model_path)
        joblib.dump(x_scaler, scaler_path)
        state_meta_path.write_text("\n".join(state_cols), encoding="utf-8")
        input_meta_path.write_text("\n".join(input_cols), encoding="utf-8")
        
        print(f"\n  动态模型已保存: {model_path}")
        
        # ── 留一批次开环验证 ──────────────────────────────────────────
        print("\n[验证] 留一批次开环预测验证...")
        val_run_id = test_runs[0]  # 取测试集第一个批次
        df_val_run = df[df["run_id"] == val_run_id].sort_values("t_h").reset_index(drop=True)
        val_steps = min(20, len(df_val_run) - 1)

        # 真实状态轨迹（t=0 ~ t=val_steps）
        true_states = df_val_run[state_cols].values  # shape (T, n_states)

        # 从真实 t=0 出发做开环滚动预测
        x_ol = true_states[0].copy()
        open_loop_preds = [x_ol.copy()]
        for t in range(val_steps):
            # 使用该步真实控制输入（若存在）；否则用零控制
            if len(control_cols) > 0 and all(c in df_val_run.columns for c in control_cols):
                u_t = df_val_run[control_cols].values[t]
            else:
                u_t = np.zeros(len(control_cols))
            inp = np.concatenate([x_ol, u_t]).reshape(1, -1)
            inp_scaled = x_scaler.transform(inp)
            x_ol = model.predict(inp_scaled).reshape(-1)
            open_loop_preds.append(x_ol.copy())

        open_loop_preds = np.array(open_loop_preds)  # (val_steps+1, n_states)
        true_slice = true_states[:val_steps + 1]

        # 计算每个变量逐步 RMSE
        ol_rmse_per_var = {}
        for i, col in enumerate(state_cols):
            rmse_i = float(np.sqrt(np.mean((open_loop_preds[:, i] - true_slice[:, i]) ** 2)))
            ol_rmse_per_var[col] = round(rmse_i, 4)
        print(f"  开环预测 RMSE（{val_steps}步，批次run_id={val_run_id}）:")
        for col, val in ol_rmse_per_var.items():
            print(f"    {col}: {val}")

        # 保存开环验证结果供前端展示
        ol_result = []
        for t in range(val_steps + 1):
            row = {"time_step": t}
            for i, col in enumerate(state_cols):
                row[f"pred_{col}"] = round(float(open_loop_preds[t, i]), 4)
                row[f"true_{col}"] = round(float(true_slice[t, i]), 4)
            ol_result.append(row)
        ol_df = pd.DataFrame(ol_result)
        ol_csv_path = WORKFLOW_OUTPUT_DIR / "mpc" / "open_loop_validation.csv"
        (WORKFLOW_OUTPUT_DIR / "mpc").mkdir(parents=True, exist_ok=True)
        ol_df.to_csv(ol_csv_path, index=False, encoding="utf-8-sig")

        ol_rmse_json_path = WORKFLOW_OUTPUT_DIR / "mpc" / "open_loop_rmse.json"
        with open(ol_rmse_json_path, "w", encoding="utf-8") as f:
            json.dump({"run_id": int(val_run_id), "steps": val_steps, "rmse": ol_rmse_per_var}, f, indent=2)
        print(f"  开环验证结果已保存")
        # ── 留一批次验证结束 ─────────────────────────────────────────────
        
        # 计算各状态变量的实验标准差
        experimental_std = {}
        for col in state_cols:
            std_val = float(df[col].std())
            experimental_std[col] = round(std_val, 4)
        
        print(f"\n实验标准差:")
        for col, std_val in experimental_std.items():
            print(f"  {col}: {std_val}")

        # 步骤3：MPC优化
        print("\n[步骤 3/3] MPC优化...")
        mpc_dir = WORKFLOW_OUTPUT_DIR / "mpc"
        mpc_dir.mkdir(parents=True, exist_ok=True)
        
        # 加载动态模型
        dynamics_model = NextStateModel(
            model_path=model_path,
            scaler_path=scaler_path,
            state_columns_path=state_meta_path,
            input_columns_path=input_meta_path,
        )
        
        # 先进行可信度评估（在MPC配置之前）
        from mpc.credibility import CredibilityAssessor, print_credibility_report
        from mpc.credibility_extended import (
            VariableCredibilityAssessor,
            MultiStepCredibilityAssessor,
            ControlCredibilityAssessor,
            TotalCredibilityAssessor,
            generate_credibility_report,
        )
        
        print("\n" + "="*80)
        print("可信度评估（完整版）")
        print("="*80)
        
        # 1. 变量级可信度
        print("\n[1/4] 变量级可信度评估...")
        var_assessor = VariableCredibilityAssessor(experimental_std, test_metrics)
        variable_credibilities = var_assessor.get_all_credibilities()
        variable_score = var_assessor.get_average_score()
        print(f"  平均变量可信度分数: {variable_score}")
        for var_name, info in variable_credibilities.items():
            print(f"    {var_name}: {info.level} (score={info.score}, weight={info.weight})")
        
        # 2. 多步预测可信度（基于开环验证结果）
        print("\n[2/4] 多步预测可信度评估...")
        multi_step_assessor = MultiStepCredibilityAssessor(
            state_cols,
            experimental_std,
            prediction_horizon=request.mpc_settings.prediction_horizon
        )
        
        # 从开环验证结果计算多步可信度
        multi_step_info = multi_step_assessor.assess_from_open_loop_validation(
            open_loop_preds,
            true_slice
        )
        print(f"  多步预测可信度: {multi_step_info.level} (score={multi_step_info.score})")
        print(f"    1步RMSE: {multi_step_info.rmse_1_step}")
        print(f"    3步RMSE: {multi_step_info.rmse_3_step}")
        print(f"    平均RMSE: {multi_step_info.rmse_horizon}")
        print(f"    误差增长率: {multi_step_info.horizon_error_growth}")
        print(f"    关键窗口稳定性: {multi_step_info.decision_window_stability}")
        
        # 3. 先运行MPC仿真获得轨迹，然后评估控制级可信度
        print("\n[3/4] MPC仿真...")
        
        # 临时配置MPC（不含总体可信度信息）
        mpc_config_temp = MPCConfig(
            prediction_horizon=request.mpc_settings.prediction_horizon,
            control_horizon=request.mpc_settings.control_horizon,
            weight_titer=request.mpc_settings.weight_titer,
            weight_vcd=request.mpc_settings.weight_vcd,
            weight_control=request.mpc_settings.weight_control,
            use_credibility=True,
            experimental_std=experimental_std,
            test_metrics=test_metrics,
        )
        
        controller = MPCController(dynamics_model, mpc_config_temp)
        
        # 初始状态：使用测试集第一个批次的真实 t=0 状态
        x0 = df[df["run_id"] == test_runs[0]].sort_values("t_h").iloc[0][state_cols].values.astype(float)
        print(f"  初始状态（来自真实批次 run_id={test_runs[0]}）: {x0}")
        print(f"  仿真步数: {request.mpc_settings.simulation_steps}")
        
        # 运行MPC仿真
        state_traj, control_traj, info_list = simulate_mpc_closed_loop(
            controller,
            x0,
            request.mpc_settings.simulation_steps,
            verbose=False,
        )
        
        # 4. 控制级可信度评估（基于MPC输出）
        print("\n[4/4] 控制级可信度评估...")
        control_assessor = ControlCredibilityAssessor(
            state_cols,
            control_cols,
            state_bounds=None,
            control_bounds=None
        )
        
        control_info = control_assessor.assess_from_mpc_output(
            state_traj,
            control_traj,
            previous_control=None
        )
        print(f"  控制级可信度: {control_info.level} (score={control_info.score})")
        print(f"    约束违反风险: {control_info.constraint_violation_risk}")
        print(f"    补料变化率: {control_info.feed_change_rate}")
        print(f"    策略稳定性: {control_info.strategy_stability}")
        
        # 5. 总体可信度评估
        print("\n[5/5] 总体可信度评估...")
        total_assessor = TotalCredibilityAssessor(
            variable_weight=0.4,
            multi_step_weight=0.3,
            control_weight=0.3
        )
        
        total_info = total_assessor.assess(
            variable_credibilities,
            multi_step_info,
            control_info
        )
        print(f"  总体可信度: {total_info.level} (score={total_info.score})")
        print(f"    推荐动作: {total_info.action}")
        print(f"    推荐理由: {total_info.reason}")
        print(f"    变量分数: {total_info.variable_score}")
        print(f"    多步分数: {total_info.multi_step_score}")
        print(f"    控制分数: {total_info.control_score}")
        
        # 生成完整报告
        credibility_report = generate_credibility_report(
            variable_credibilities,
            multi_step_info,
            control_info,
            total_info
        )
        
        print("\n" + "="*80)
        
        # 保存轨迹
        np.save(mpc_dir / "state_trajectory.npy", state_traj)
        np.save(mpc_dir / "control_trajectory.npy", control_traj)
        
        # 生成补料建议
        recommendations = []
        control_cols_mpc = [c for c in input_cols if c not in state_cols]
        
        for t in range(len(control_traj)):
            rec = {"time_step": t}
            for i, col in enumerate(state_cols):
                rec[f"预测_{col}"] = float(state_traj[t, i])
            for i, col in enumerate(control_cols_mpc):
                if i < len(control_traj[t]):
                    rec[col] = float(control_traj[t, i])  # 直接使用列名，不加"建议_"前缀
            recommendations.append(rec)
        
        df_rec = pd.DataFrame(recommendations)
        csv_path = mpc_dir / "feeding_recommendations.csv"
        df_rec.to_csv(csv_path, index=False, encoding="utf-8-sig")
        
        print(f"\n  补料策略已保存: {csv_path}")
        
        # 构建结果
        results = {
            "data_shape": list(df.shape),
            "n_runs": int(df["run_id"].nunique()),
            "dynamics": {
                "model_type": request.model_settings.dynamics_model_type,
                "state_columns": state_cols,
                "input_columns": input_cols,
                "train_samples": int(X_train.shape[0]),
                "test_r2": "见日志",
                "train_metrics": train_metrics,
                "val_metrics": val_metrics,
                "test_metrics": test_metrics,
                "experimental_std": experimental_std,
            },
            "mpc": {
                "simulation_steps": request.mpc_settings.simulation_steps,
                "state_trajectory_shape": list(state_traj.shape),
                "control_trajectory_shape": list(control_traj.shape),
                "x0_run_id": int(test_runs[0]),
            },
            "open_loop_validation": {
                "run_id": int(val_run_id),
                "steps": val_steps,
                "rmse": ol_rmse_per_var,
            },
            "credibility": credibility_report,
        }
        
        # 保存结果
        api_results_file = RESULTS_DIR / f"results_{timestamp}.json"
        with open(api_results_file, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

        TRAINED_IN_SESSION = True
        LAST_TRAIN_RESULT_FILE = str(api_results_file)
        PREDICT_MODEL_CACHE["dynamics_dir"] = None
        PREDICT_MODEL_CACHE["model"] = None
        PREDICT_MODEL_CACHE["scaler"] = None
        PREDICT_MODEL_CACHE["state_cols"] = None
        PREDICT_MODEL_CACHE["input_cols"] = None
        
        print("\n" + "="*80)
        print("训练完成！")
        print("="*80)
        
        return {
            "success": True,
            "workspace": str(WORKFLOW_OUTPUT_DIR),
            "results_file": str(api_results_file),
            "results": results,
            "message": "训练完成"
        }
    
    except Exception as e:
        import traceback
        error_detail = f"训练失败: {str(e)}\n{traceback.format_exc()}"
        print(error_detail)
        raise HTTPException(
            status_code=500,
            detail=error_detail
        )


@app.post("/api/train/submit")
async def submit_train_job(request: TrainRequest):
    job_id = uuid.uuid4().hex
    _set_training_job(
        job_id,
        status="queued",
        dataset_name=request.dataset_name,
        created_at=datetime.now().isoformat(),
        started_at=None,
        finished_at=None,
        result=None,
        error=None,
    )

    def run_job():
        _set_training_job(job_id, status="running", started_at=datetime.now().isoformat())
        try:
            result = asyncio.run(train_models(request))
            _set_training_job(
                job_id,
                status="completed",
                finished_at=datetime.now().isoformat(),
                result=result,
            )
        except HTTPException as exc:
            detail = exc.detail if isinstance(exc.detail, str) else json.dumps(exc.detail, ensure_ascii=False)
            _set_training_job(
                job_id,
                status="failed",
                finished_at=datetime.now().isoformat(),
                error=detail,
            )
        except Exception as exc:
            _set_training_job(
                job_id,
                status="failed",
                finished_at=datetime.now().isoformat(),
                error=str(exc),
            )

    threading.Thread(target=run_job, daemon=True).start()

    return {
        "success": True,
        "job_id": job_id,
        "status": "queued",
        "message": "训练任务已提交，请轮询任务状态。"
    }


@app.get("/api/train/jobs/{job_id}")
async def get_train_job(job_id: str):
    job = _get_training_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="训练任务不存在")

    return jsonable_encoder({
        "success": True,
        **job,
    })


@app.get("/api/results/{result_id}")
async def get_results(result_id: str):
    """获取训练结果"""
    try:
        results_file = RESULTS_DIR / f"results_{result_id}.json"
        if not results_file.exists():
            raise HTTPException(status_code=404, detail="结果不存在")
        
        with open(results_file, "r", encoding="utf-8") as f:
            results = json.load(f)
        
        return {
            "success": True,
            "results": results
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/feeding-strategy")
async def get_feeding_strategy():
    """获取最新的补料策略"""
    try:
        feeding_file = WORKFLOW_OUTPUT_DIR / "mpc" / "feeding_recommendations.csv"
        
        if not feeding_file.exists():
            raise HTTPException(status_code=404, detail="补料策略尚未生成，请先训练模型")
        
        df = pd.read_csv(feeding_file)
        
        return {
            "success": True,
            "recommendations": df.to_dict(orient="records"),
            "summary": {
                "total_steps": len(df),
                "avg_feed_glc": float(df["Feed_Glc"].mean()) if "Feed_Glc" in df.columns else 0,
                "avg_feed_gln": float(df["Feed_Gln"].mean()) if "Feed_Gln" in df.columns else 0
            }
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/trajectories")
async def get_trajectories():
    """获取状态和控制轨迹"""
    try:
        state_file = WORKFLOW_OUTPUT_DIR / "mpc" / "state_trajectory.npy"
        control_file = WORKFLOW_OUTPUT_DIR / "mpc" / "control_trajectory.npy"
        
        if not state_file.exists() or not control_file.exists():
            raise HTTPException(status_code=404, detail="轨迹数据尚未生成")
        
        state_traj = np.load(state_file)
        control_traj = np.load(control_file)
        
        # 读取列名
        dynamics_dir = WORKFLOW_OUTPUT_DIR / "dynamics_rf"
        if not dynamics_dir.exists():
            dynamics_dir = WORKFLOW_OUTPUT_DIR / "dynamics"
        
        state_cols_file = dynamics_dir / "state_columns.txt"
        if state_cols_file.exists():
            state_cols = state_cols_file.read_text().strip().split("\n")
        else:
            state_cols = ["VCD", "Glc", "Gln", "Amm", "Lac", "BRvol"]
        
        input_cols_file = dynamics_dir / "input_columns.txt"
        if input_cols_file.exists():
            input_cols = input_cols_file.read_text().strip().split("\n")
            # 控制列是输入列中不在状态列中的
            control_cols = [c for c in input_cols if c not in state_cols]
        else:
            control_cols = ["temp", "pH"]
        
        # 构建轨迹数据
        state_trajectory = []
        for i, state in enumerate(state_traj):
            state_dict = {"time_step": i}
            for j, col in enumerate(state_cols):
                if j < len(state):
                    state_dict[col] = float(state[j])
            state_trajectory.append(state_dict)
        
        control_trajectory = []
        for i, control in enumerate(control_traj):
            control_dict = {"time_step": i}
            for j, col in enumerate(control_cols):
                if j < len(control):
                    control_dict[col] = float(control[j])
            control_trajectory.append(control_dict)
        
        return {
            "success": True,
            "state_trajectory": state_trajectory,
            "control_trajectory": control_trajectory,
            "state_columns": state_cols,
            "control_columns": control_cols
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/model-info")
async def get_model_info():
    """获取已训练模型的信息"""
    try:
        info = {
            "soft_sensor": {},
            "dynamics": {},
            "mpc": {}
        }
        
        # 软传感器信息
        soft_sensor_dir = WORKFLOW_OUTPUT_DIR / "soft_sensor"
        if soft_sensor_dir.exists():
            metadata_file = soft_sensor_dir / "model_metadata.txt"
            if metadata_file.exists():
                metadata = {}
                for line in metadata_file.read_text().split("\n"):
                    if ":" in line:
                        key, val = line.split(":", 1)
                        metadata[key.strip()] = val.strip()
                info["soft_sensor"] = metadata
        
        # 动态模型信息
        for dynamics_dir_name in ["dynamics_rf", "dynamics_nn", "dynamics_gp", "dynamics"]:
            dynamics_dir = WORKFLOW_OUTPUT_DIR / dynamics_dir_name
            if dynamics_dir.exists():
                state_cols_file = dynamics_dir / "state_columns.txt"
                input_cols_file = dynamics_dir / "input_columns.txt"
                if state_cols_file.exists():
                    info["dynamics"]["state_columns"] = state_cols_file.read_text().strip().split("\n")
                if input_cols_file.exists():
                    info["dynamics"]["input_columns"] = input_cols_file.read_text().strip().split("\n")
                break
        
        return {
            "success": True,
            "model_info": info
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/download/feeding-strategy")
async def download_feeding_strategy():
    """下载补料策略CSV文件"""
    try:
        feeding_file = WORKFLOW_OUTPUT_DIR / "mpc" / "feeding_recommendations.csv"
        
        if not feeding_file.exists():
            raise HTTPException(status_code=404, detail="补料策略文件不存在")
        
        return FileResponse(
            path=feeding_file,
            filename="feeding_recommendations.csv",
            media_type="text/csv"
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/open-loop-validation")
async def get_open_loop_validation():
    """获取留一批次开环预测验证结果"""
    try:
        rmse_file = WORKFLOW_OUTPUT_DIR / "mpc" / "open_loop_rmse.json"
        traj_file = WORKFLOW_OUTPUT_DIR / "mpc" / "open_loop_validation.csv"

        if not rmse_file.exists():
            raise HTTPException(status_code=404, detail="开环验证结果尚未生成，请先训练模型")

        with open(rmse_file, "r", encoding="utf-8") as f:
            rmse_data = json.load(f)

        traj_data = []
        if traj_file.exists():
            df_traj = pd.read_csv(traj_file)
            traj_data = df_traj.to_dict(orient="records")

        return {
            "success": True,
            "run_id": rmse_data.get("run_id"),
            "steps": rmse_data.get("steps"),
            "rmse": rmse_data.get("rmse", {}),
            "trajectory": traj_data,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 模型行为探查接口 ====================

def _load_training_dataframe():
    dataset_path = None
    result_files = sorted(RESULTS_DIR.glob("results_*.json"), reverse=True)
    for result_file in result_files:
        try:
            with open(result_file, "r", encoding="utf-8") as f:
                results = json.load(f)
            dataset_name = results.get("dataset_name")
            if dataset_name:
                candidate = UPLOAD_DIR / dataset_name
                if candidate.exists():
                    dataset_path = candidate
                    break
        except Exception:
            continue

    if dataset_path is None:
        upload_files = sorted(UPLOAD_DIR.glob("*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
        if upload_files:
            dataset_path = upload_files[0]

    if dataset_path is None or not dataset_path.exists():
        raise HTTPException(status_code=404, detail="未找到可用于统计分析的训练数据集")

    df = pd.read_csv(dataset_path)
    return df, dataset_path.name


def _safe_float(v):
    if pd.isna(v):
        return None
    try:
        fv = float(v)
    except Exception:
        return None
    if math.isfinite(fv):
        return round(fv, 6)
    return None


@app.get("/api/training-data-distribution")
async def get_training_data_distribution():
    """返回训练集各指标原始数据分布与基础统计信息"""
    try:
        df, dataset_name = _load_training_dataframe()

        excluded_cols = {
            "run_id", "t_h", "timestamps", "time_step", "group", "var"
        }
        feature_cols = [
            c for c in df.columns
            if c not in excluded_cols and pd.api.types.is_numeric_dtype(df[c])
        ]

        distributions = []
        for col in feature_cols:
            series = pd.to_numeric(df[col], errors="coerce").dropna()
            if series.empty:
                continue

            q1 = float(series.quantile(0.25))
            q2 = float(series.quantile(0.50))
            q3 = float(series.quantile(0.75))
            min_v = float(series.min())
            max_v = float(series.max())
            mean_v = float(series.mean())
            std_v = float(series.std()) if len(series) > 1 else 0.0
            bins = min(18, max(8, int(math.sqrt(len(series)))))
            hist, edges = np.histogram(series, bins=bins)

            distributions.append({
                "feature": col,
                "count": int(series.shape[0]),
                "mean": round(mean_v, 4),
                "std": round(std_v, 4),
                "min": round(min_v, 4),
                "q1": round(q1, 4),
                "median": round(q2, 4),
                "q3": round(q3, 4),
                "max": round(max_v, 4),
                "histogram": {
                    "counts": [int(x) for x in hist.tolist()],
                    "edges": [round(float(x), 6) for x in edges.tolist()],
                },
                "boxplot": [
                    round(min_v, 4),
                    round(q1, 4),
                    round(q2, 4),
                    round(q3, 4),
                    round(max_v, 4),
                ],
                "sample_values": [
                    _safe_float(v) for v in series.head(80).tolist() if _safe_float(v) is not None
                ],
            })

        return jsonable_encoder({
            "success": True,
            "dataset_name": dataset_name,
            "rows": int(len(df)),
            "runs": int(df["run_id"].nunique()) if "run_id" in df.columns else None,
            "features": distributions,
        })

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"训练集分布统计失败: {str(e)}")

class PredictRequest(BaseModel):
    """单步预测请求"""
    VCD: float = 5.0
    Glc: float = 5.0
    Gln: float = 2.0
    Amm: float = 1.0
    Lac: float = 5.0
    Titer: float = 500.0
    DCD: float = 0.5
    Lysed: float = 0.05
    Feed_Glc: float = 0.5
    Feed_Gln: float = 0.2
    Feed_BRvol: float = 0.0
    temp: float = 37.0
    pH: float = 7.2
    DO: float = 50.0
    Stir: float = 100.0


def _load_cached_predict_resources():
    import joblib

    dynamics_dir = None
    for name in ["dynamics_rf", "dynamics_nn", "dynamics_gp", "dynamics"]:
        d = WORKFLOW_OUTPUT_DIR / name
        if d.exists() and (d / "next_state_model.joblib").exists():
            dynamics_dir = d
            break

    if dynamics_dir is None:
        raise HTTPException(
            status_code=404,
            detail="动态模型尚未训练，请先完成训练流程"
        )

    cache_hit = (
        PREDICT_MODEL_CACHE["dynamics_dir"] == str(dynamics_dir)
        and PREDICT_MODEL_CACHE["model"] is not None
        and PREDICT_MODEL_CACHE["scaler"] is not None
        and PREDICT_MODEL_CACHE["state_cols"] is not None
        and PREDICT_MODEL_CACHE["input_cols"] is not None
    )

    if not cache_hit:
        PREDICT_MODEL_CACHE["dynamics_dir"] = str(dynamics_dir)
        PREDICT_MODEL_CACHE["model"] = joblib.load(dynamics_dir / "next_state_model.joblib")
        PREDICT_MODEL_CACHE["scaler"] = joblib.load(dynamics_dir / "x_scaler.joblib")
        PREDICT_MODEL_CACHE["state_cols"] = (dynamics_dir / "state_columns.txt").read_text(encoding="utf-8").strip().split("\n")
        PREDICT_MODEL_CACHE["input_cols"] = (dynamics_dir / "input_columns.txt").read_text(encoding="utf-8").strip().split("\n")

    return (
        PREDICT_MODEL_CACHE["model"],
        PREDICT_MODEL_CACHE["scaler"],
        PREDICT_MODEL_CACHE["state_cols"],
        PREDICT_MODEL_CACHE["input_cols"],
    )


@app.post("/api/predict-next-state")
async def predict_next_state(request: PredictRequest):
    """
    使用已训练的动态模型预测下一时间步的状态变量。
    供前端「模型行为探查」面板实时调用。
    """
    try:
        model, scaler, state_cols, input_cols = _load_cached_predict_resources()

        # 构建输入向量（按训练时的 input_cols 顺序）
        req_dict = request.model_dump()
        inp_vec = np.array([req_dict.get(col, 0.0) for col in input_cols], dtype=float).reshape(1, -1)

        # 标准化 + 预测
        inp_scaled = scaler.transform(inp_vec)
        pred = model.predict(inp_scaled).reshape(-1)

        # 构建输出字典
        prediction = {col: round(float(pred[i]), 4) for i, col in enumerate(state_cols)}

        return {
            "success": True,
            "prediction": prediction,
            "state_columns": state_cols,
            "input_columns": input_cols,
        }

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        raise HTTPException(status_code=500, detail=f"预测失败: {str(e)}\n{traceback.format_exc()}")


@app.get("/api/inspector-meta")
async def get_inspector_meta():
    """
    返回已训练模型的元信息供前端探查面板展示：
    模型类型、状态列、输入列、测试集 R² / RMSE 等。
    """
    try:
        # 查找最新结果文件
        result_files = sorted(RESULTS_DIR.glob("results_*.json"), reverse=True)
        if not result_files:
            raise HTTPException(status_code=404, detail="尚无训练结果")

        with open(result_files[0], "r", encoding="utf-8") as f:
            results = json.load(f)

        dynamics = results.get("dynamics", {})
        test_metrics = dynamics.get("test_metrics", {})

        # 计算平均 R²
        r2_vals = [v["r2"] for v in test_metrics.values() if "r2" in v]
        avg_r2 = round(float(np.mean(r2_vals)), 3) if r2_vals else None

        return {
            "success": True,
            "model_type": dynamics.get("model_type", "rf"),
            "state_columns": dynamics.get("state_columns", []),
            "input_columns": dynamics.get("input_columns", []),
            "test_metrics": test_metrics,
            "experimental_std": dynamics.get("experimental_std", {}),
            "avg_r2": avg_r2,
            "n_features": len(dynamics.get("input_columns", [])),
            "trained_in_session": TRAINED_IN_SESSION,
            "last_train_result_file": LAST_TRAIN_RESULT_FILE,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/{full_path:path}")
async def spa_fallback(full_path: str):
    """生产环境下返回前端 SPA 页面"""
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="接口不存在")
    index_file = FRONTEND_DIST_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    raise HTTPException(status_code=404, detail="前端构建产物不存在，请先执行 npm run build")


if __name__ == "__main__":
    import uvicorn
    print("="*80)
    print("CHO细胞培养优化系统 - 后端服务器")
    print("="*80)
    print("API文档: http://localhost:8000/docs")
    print("前端地址: http://localhost:5173")
    print("="*80)
    uvicorn.run(app, host="0.0.0.0", port=8000)
