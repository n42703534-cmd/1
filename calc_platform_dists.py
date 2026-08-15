import math
import sys

# ==============================================================================
# calc_platform_dists.py (带交互式工况选单的最终版)
# 专门用于计算车门到楼扶梯距离的独立工具 (基于 Pathfinder 二维坐标系)
# ==============================================================================

# 1. 填入你从 Pathfinder 里直接取到的 (X, Y) 坐标！
PATHFINDER_CONFIG = {
    "L7": {
        "cars": 6,
        "doors_per_car": 5,
        "trains": [
            {"name": "Train_Up", "start_pos": (-5541.481, -9480.794), "end_pos": (-5407.951, -9473.857)},
            {"name": "Train_Down", "start_pos": (-5540.689, -9492.055), "end_pos": (-5407.423, -9485.382)}
        ],
        "verticals": {
            "Stair_L7_1": (-5502.64, -9479.39),
            "Escalator_L7_up1": (-5504.62, -9481.59),
            "Stair_L7_2": (-5482.78, -9480.12),
            "Stair_L7_3": (-5442.65, -9475.86),
            "Escalator_L7_down1": (-5442.75, -9477.91),
        }
    },

    "L2": {
        "cars": 8,
        "doors_per_car": 5,
        "trains": [
            {"name": "Train_1", "start_pos": (-5571.67, -9541.11), "end_pos": (-5417.93, -9530.43)},
            {"name": "Train_2", "start_pos": (-5570.64, -9553.27), "end_pos": (-5416.95, -9542.64)}
        ],
        "verticals": {
            "Stair_L2_1": (-5551.17, -9545.93),
            "Stair_L2_2": (-5551.17, -9547.86),
            "Stair_L2_3": (-5525.22, -9543.65),
            "Escalator_L2_up1": (-5525.13, -9546.28),
            "Escalator_L2_down1": (-5457.34, -9539.15),
            "Stair_L2_4": (-5457.53, -9540.86),
            "Stair_L2_5": (-5434.03, -9536.58),
            "Stair_L2_6": (-5433.81, -9539.00),
        }
    },

    # ==========================================
    # 16号线 - 岛台1 (不互通的独立区域A)
    # ==========================================
    "L16_Island1": {
        "cars": 6,
        "doors_per_car": 3,  # 单侧开门，每节3个有效门
        "trains": [
            {"name": "Train_1", "start_pos": (-5493.03, -9633.52), "end_pos": (-5353.0, -9633.39)},  # 待填：列车1头尾坐标
            {"name": "Train_2", "start_pos": (-5492.95, -9647.53), "end_pos": (-5353.06, -9647.47)}  # 待填：列车2头尾坐标
        ],
        "verticals": {
            "Stair_L16_1": (-5454.98, -9639.79),
            "Escalator_L16_up1": (-5454.62, -9641.94),
            "Escalator_L16_down1": (-5416.98, -9639.72),
            "Escalator_L16_down2": (-5416.89, -9642.03),
            "Stair_L16_2": (-5392.08, -9640.16),
            "Escalator_L16_up2": (-5392.08, -9641.97),
        }
    },

    # ==========================================
    # 16号线 - 岛台2 (不互通的独立区域B)
    # ==========================================
    "L16_Island2": {
        "cars": 6,
        "doors_per_car": 3,  # 单侧开门，每节3个有效门
        "trains": [
            {"name": "Train_3", "start_pos": (-5493.06, -9651.59), "end_pos": (-5353.06, -9651.38)},  # 待填：列车3头尾坐标
            {"name": "Train_4", "start_pos": (-5492.94, -9662.63), "end_pos": (-5353.1, -9662.6)}  # 待填：列车4头尾坐标
        ],
        "verticals": {
            "Escalator_L16_up3": (-5454.64, -9657.22),
            "Stair_L16_3": (-5454.89, -9659.50),
            "Escalator_L16_down3": (-5417.03, -9657.39),
            "Escalator_L16_down4": (-5417.03, -9659.39),
            "Escalator_L16_up4": (-5392.06, -9657.29),
            "Stair_L16_4": (-5391.63, -9659.19),
        }
    },

    "L18": {
        "cars": 6,
        "doors_per_car": 5,
        "trains": [
            {"name": "Train_1", "start_pos": (-5586.95, -9699.52), "end_pos": (-5545.42, -9824.71)},
            {"name": "Train_2", "start_pos": (-5601.2, -9704.3), "end_pos": (-5559.2, -9829.33)}
        ],
        "verticals": {
            "Escalator_L18_down1": (-5584.26, -9721.95),
            "Escalator_L18_up1": (-5585.77, -9722.59),
            "Stair_L18_1": (-5587.67, -9723.14),
            "Escalator_L18_up2": (-5589.6, -9724.14),

            "Escalator_L18_down2": (-5576.07, -9748.08),
            "Escalator_L18_up3": (-5577.76, -9748.7),

            "Escalator_L18_down3": (-5571.27, -9775.25),
            "Escalator_L18_up4": (-5569.68, -9774.84),
            "Escalator_L18_up5": (-5567.99, -9774.42),

            "Escalator_L18_down4": (-5563.09, -9801.27),
            "Stair_L18_2": (-5560.82, -9800.57),
            "Escalator_L18_up6": (-5559.01, -9800.03),

            "Escalator_L18_up7": (-5557.50, -9817.48),
            "Escalator_L18_up8": (-5555.65, -9816.96),
            "Escalator_L18_up9": (-5553.93, -9816.29),
        }
    },

    "Maglev": {
        "cars": 5,  # 5节车厢
        "doors_per_car": 2,  # 🌟 每侧车厢有2个门。我们用下面 4 排线来代表全开的车门！
        "trains": [
            # 第一列车 (双侧车门全开)
            {"name": "Train_1_Left_Doors", "start_pos": (-5480.96, -9583.00), "end_pos": (-5352.24, -9582.92)},  # 待填：列车1左侧车门头尾坐标
            {"name": "Train_1_Right_Doors", "start_pos": (-5481.08, -9588.17), "end_pos": (-5352.29, -9588.10)},  # 待填：列车1右侧车门头尾坐标

            # 第二列车 (双侧车门全开)
            {"name": "Train_2_Left_Doors", "start_pos": (-5480.88, -9594.91), "end_pos": (-5352.40, -9594.92)},  # 待填：列车2左侧车门头尾坐标
            {"name": "Train_2_Right_Doors", "start_pos": (-5481.02, -9600.07), "end_pos": (-5352.29, -9600.10)}  # 待填：列车2右侧车门头尾坐标
        ],
        "verticals": {
            "Escalator_Maglev_down1": (-5465.99, -9575.25),
            "Stair_Maglev_1": (-5466.71, -9576.80),
            "Escalator_Maglev_down2": (-5439.71, -9575.18),
            "Stair_Maglev_2": (-5439.71, -9576.71),
            "Stair_Maglev_3": (-5466.59, -9606.76),
            "Escalator_Maglev_down3": (-5466.42, -9608.63),
            "Stair_Maglev_4": (-5439.85, -9607.01),
            "Escalator_Maglev_down4": (-5439.88, -9608.72),
            "Stair_Maglev_5": (-5497.98, -9592.71),
            "Escalator_Maglev_up1": (-5498.04, -9591.51),
            "Stair_Maglev_6": (-5408.16, -9593.19),
            "Escalator_Maglev_up2": (-5408.04, -9590.85),
        }
    }
}


def get_user_choice():
    print("\n" + "=" * 55)
    print("🚇 欢迎使用站台距离自动计算工具 (Pathfinder 版)")
    print("=" * 55)
    print("请选择你要计算的疏散工况：\n")
    print("  [1] 单侧列车疏散 (仅计算第 1 列车，如上行线)")
    print("  [2] 单侧列车疏散 (仅计算第 2 列车，如下行线)")
    print("  [3] 双侧列车同时疏散 (计算全站台双侧所有车门)")
    print("-" * 55)

    while True:
        choice = input("👉 请输入序号 [1 / 2 / 3] 并按回车: ").strip()
        if choice in ['1', '2', '3']:
            return int(choice)
        print("❌ 输入无效，请重新输入 1, 2 或 3！")


def generate_door_positions(start_pos, end_pos, total_doors):
    start_x, start_y = start_pos
    end_x, end_y = end_pos
    doors = []
    if total_doors <= 1:
        return [start_pos]

    for i in range(total_doors):
        ratio = i / (total_doors - 1)
        dx = start_x + ratio * (end_x - start_x)
        dy = start_y + ratio * (end_y - start_y)
        doors.append((dx, dy))
    return doors


def calculate_average_distance(all_door_positions, stair_pos):
    total_dist = 0.0
    sx, sy = stair_pos
    for dx, dy in all_door_positions:
        dist = math.sqrt((dx - sx) ** 2 + (dy - sy) ** 2)
        total_dist += dist

    if len(all_door_positions) == 0:
        return 0.0
    return total_dist / len(all_door_positions)


def generate_distance_dict(scenario_mode):
    final_dict = {}
    for line_id, config in PATHFINDER_CONFIG.items():
        total_doors_per_train = config["cars"] * config["doors_per_car"]

        all_active_doors = []
        for train in config["trains"]:
            # 🌟 智能过滤逻辑：通过列车名字识别它属于“单侧1”还是“单侧2”
            train_name = train["name"]
            is_train_1 = "Train_1" in train_name or "Train_Up" in train_name or "Train_3" in train_name
            is_train_2 = "Train_2" in train_name or "Train_Down" in train_name or "Train_4" in train_name

            if scenario_mode == 1 and not is_train_1:
                continue  # 选了1，那就跳过第2列车
            if scenario_mode == 2 and not is_train_2:
                continue  # 选了2，那就跳过第1列车
            # 如果选了3，什么都不跳过，全部计算

            if train["start_pos"] == (0.0, 0.0) and train["end_pos"] == (0.0, 0.0):
                continue

            train_doors = generate_door_positions(train["start_pos"], train["end_pos"], total_doors_per_train)
            all_active_doors.extend(train_doors)

        for v_name, stair_pos in config["verticals"].items():
            if stair_pos == (0.0, 0.0):
                continue

            # 计算合并后的总平均距离
            avg_dist = calculate_average_distance(all_active_doors, stair_pos)
            final_dict[v_name] = round(avg_dist, 2)

    return final_dict


if __name__ == "__main__":
    # 1. 弹出菜单让用户选择
    mode = get_user_choice()

    # 2. 根据选择进行计算
    result = generate_distance_dict(mode)

    # 3. 打印结果
    mode_text = {1: "单侧 (列车1)", 2: "单侧 (列车2)", 3: "双侧同时"}[mode]
    print(f"\n✅ 计算完成！当前工况：[{mode_text}疏散]")
    print("====== 请将以下字典复制并替换到 lines_config.py 底部 ======\n")
    print("PRECALCULATED_PLATFORM_DISTS = {")
    for k, v in result.items():
        print(f'    "{k}": {v},')
    print("}")
    print("\n===========================================================")