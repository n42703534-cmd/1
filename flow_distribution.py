"""
人流分配模块
-------------
1️⃣ 总人数先均分（宏观）
2️⃣ 再按设施偏好比例分配（行为）
"""

def normalize(weights: dict):
    s = sum(weights.values())
    return {k: v / s for k, v in weights.items()}


def distribute_platform_flow(
    total_people: int,
    preference: dict,
    source_node="Platform"
):
    """
    输入：
        total_people : 站台总人数
        preference   : 各设施偏好权重
    输出：
        CROWD_DEMAND : 可直接用于 A* 的人流字典
    """

    preference = normalize(preference)

    crowd = {}

    for facility, ratio in preference.items():
        crowd[f"{source_node}->{facility}"] = total_people * ratio

    return crowd
