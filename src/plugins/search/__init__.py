# 仅导入Nonebot 2.0+核心模块，无任何高版本依赖
from nonebot import on_command, get_bot, get_driver
from nonebot.adapters.onebot.v11 import Message, MessageEvent, GROUP, PRIVATE
from nonebot.params import CommandArg
import httpx
import asyncio
from datetime import datetime
from typing import Dict, Tuple
from .database import *

# ====================== 1. 注册指令（最基础的方式） ======================
search_cmd = on_command("search", priority=5, block=True, permission=GROUP | PRIVATE)
analysis_cmd = on_command("analysis", priority=5, block=True, permission=GROUP | PRIVATE)

# ====================== 2. 全局变量 ======================
user_hourly_queries: Dict[Tuple[int, str], int] = {}  # (用户ID, 小时标识) -> 次数
query_locks: Dict[int, asyncio.Lock] = {}  # 防重复查询锁
FREQUENT_ALERT_THRESHOLD = 5  # 1小时同一地图搜索≥5次告警


# ====================== 3. 工具函数 ======================
def get_hour_key() -> str:
    """生成当前小时标识：YYYYMMDDHH"""
    return datetime.now().strftime("%Y%m%d%H")


async def send_alert(qq: int, mapname: str, cnt: int):
    """发送频繁搜索告警到所有告警群"""
    groups = get_all_alert_groups()
    if not groups:
        return
    bot = get_bot()
    alert_msg = f"⚠️ 频繁搜索告警\n用户QQ：{qq}\n地图：{mapname}\n1小时次数：{cnt}次"
    for g in groups:
        try:
            await bot.send_group_msg(group_id=g, message=alert_msg)
        except:
            pass


# ====================== 4. 手动解析/search指令（无任何第三方解析器） ======================
def parse_search_cmd(raw_text: str) -> dict:
    """
    解析结果示例：
    - 普通查询：{"type": "query", "map_name": "骰子破敌"}
    - 添加管理员：{"type": "admin_add", "qq": 123456}
    - 移除管理员：{"type": "admin_remove", "qq": 123456}
    - 添加告警群：{"type": "admingroup_add", "group_id": 7890123}
    - 移除告警群：{"type": "admingroup_remove", "group_id": 7890123}
    - 设置次数：{"type": "times", "limit": 5}
    - 帮助：{"type": "help"}
    - 无效：{"type": "invalid"}
    - 空：{"type": "empty"}
    """
    # 去掉指令名，分割参数
    parts = raw_text.replace("search", "", 1).strip().split()
    if not parts:
        return {"type": "empty"}

    # 帮助指令
    if parts[0] in ["-h", "--help"]:
        return {"type": "help"}

    # 管理员管理：/search admin add/remove QQ
    if parts[0] == "admin":
        if len(parts) != 3 or not parts[2].isdigit():
            return {"type": "invalid"}
        action = parts[1]
        qq = int(parts[2])
        if action == "add":
            return {"type": "admin_add", "qq": qq}
        elif action == "remove":
            return {"type": "admin_remove", "qq": qq}
        else:
            return {"type": "invalid"}

    # 告警群管理：/search admingroup add/remove 群号
    if parts[0] == "admingroup":
        if len(parts) != 3 or not parts[2].isdigit():
            return {"type": "invalid"}
        action = parts[1]
        group_id = int(parts[2])
        if action == "add":
            return {"type": "admingroup_add", "group_id": group_id}
        elif action == "remove":
            return {"type": "admingroup_remove", "group_id": group_id}
        else:
            return {"type": "invalid"}

    # 次数限制：/search times 5
    if parts[0] == "times":
        if len(parts) != 2 or not parts[1].isdigit():
            return {"type": "invalid"}
        return {"type": "times", "limit": int(parts[1])}

    # 普通地图查询
    return {"type": "query", "map_name": " ".join(parts)}


# ====================== 5. 处理/search指令 ======================
@search_cmd.handle()
async def handle_search(event: MessageEvent):
    uid = event.user_id
    raw_text = event.get_plaintext().strip()
    parsed = parse_search_cmd(raw_text)

    # 空指令
    if parsed["type"] == "empty":
        await search_cmd.finish("❌ 请输入地图名称！示例：/search 骰子破敌-Hutory")

    # 帮助指令
    if parsed["type"] == "help":
        help_text = """
📖 地图查询指令帮助：
1. 普通查询：/search 地图名称
2. 管理员指令：
   - 添加管理员：/search admin add QQ号
   - 移除管理员：/search admin remove QQ号
   - 添加告警群：/search admingroup add 群号
   - 移除告警群：/search admingroup remove 群号
   - 设置小时限制：/search times 次数（≥1）
        """.strip()
        await search_cmd.finish(help_text)

    # 无效指令
    if parsed["type"] == "invalid":
        await search_cmd.finish("❌ 指令格式错误！输入 /search -h 查看帮助")

    # ---------------- 管理指令权限校验 ----------------
    admin_types = ["admin_add", "admin_remove", "admingroup_add", "admingroup_remove", "times"]
    if parsed["type"] in admin_types:
        is_current_admin = is_admin(uid)
        # 首次添加管理员无需权限
        is_first_admin = (parsed["type"] == "admin_add" and not is_current_admin)

        if not is_current_admin and not is_first_admin:
            await search_cmd.finish("❌ 仅管理员可执行该指令！")

    # ---------------- 执行管理指令 ----------------
    # 添加管理员
    if parsed["type"] == "admin_add":
        success = add_admin(parsed["qq"])
        await search_cmd.finish(f"✅ 添加管理员{'成功' if success else '失败（已存在）'}")

    # 移除管理员
    if parsed["type"] == "admin_remove":
        success = remove_admin(parsed["qq"])
        await search_cmd.finish(f"✅ 移除管理员{'成功' if success else '失败（不存在）'}")

    # 添加告警群
    if parsed["type"] == "admingroup_add":
        success = add_alert_group(parsed["group_id"])
        await search_cmd.finish(f"✅ 添加告警群{'成功' if success else '失败（已存在）'}")

    # 移除告警群
    if parsed["type"] == "admingroup_remove":
        success = remove_alert_group(parsed["group_id"])
        await search_cmd.finish(f"✅ 移除告警群{'成功' if success else '失败（不存在）'}")

    # 设置次数限制
    if parsed["type"] == "times":
        limit = parsed["limit"]
        if limit < 1:
            await search_cmd.finish("❌ 次数必须≥1！")
        success = set_hourly_limit(limit)
        await search_cmd.finish(f"✅ 每小时限制设为 {limit} 次" if success else "❌ 设置失败")

    # ---------------- 普通地图查询 ----------------
    if parsed["type"] == "query":
        map_name = parsed["map_name"]

        # 1. 频率限制
        hour_key = get_hour_key()
        user_key = (uid, hour_key)
        hourly_limit = get_hourly_limit()
        used_count = user_hourly_queries.get(user_key, 0)

        if used_count >= hourly_limit:
            await search_cmd.finish(f"❌ 每小时最多搜索 {hourly_limit} 次，请1小时后再试")

        # 2. 防重复查询
        if uid not in query_locks:
            query_locks[uid] = asyncio.Lock()
        lock = query_locks[uid]
        if lock.locked():
            await search_cmd.finish("⏳ 正在查询中，请勿重复执行")

        async with lock:
            try:
                await search_cmd.send("🔍 正在查询, 请勿重复执行\n(没用码: KmI0feM)")

                # 调用接口（根据实际情况调整）
                async with httpx.AsyncClient(timeout=10) as cli:
                    resp = await cli.get("https://atland.icu/extract", params={"name": map_name})
                    resp.raise_for_status()
                    code = resp.json().get("code", "")
                    link = f"https://atland.icu/extract?code={code}"

                # 更新次数缓存
                user_hourly_queries[user_key] = used_count + 1

                # 插入查询记录
                insert_query_record(uid, map_name)

                # 检测频繁搜索并告警
                cnt = get_user_map_query_count(uid, map_name)
                if cnt >= FREQUENT_ALERT_THRESHOLD:
                    asyncio.create_task(send_alert(uid, map_name, cnt))

                # 返回结果
                await search_cmd.send(f"✅ 查询成功\n{link}\n有效期180秒\n(没用码: YT60Vqc)")

            except Exception as ex:
                await search_cmd.finish(f"❌ 查询失败：{str(ex)}")


# ====================== 6. 处理/analysis指令（管理员专属） ======================
@analysis_cmd.handle()
async def handle_analysis(event: MessageEvent, args: Message = CommandArg()):
    if not is_admin(event.user_id):
        await analysis_cmd.finish("❌ 仅管理员可使用该指令！")

    map_name = args.extract_plain_text().strip()
    if map_name:
        count = get_query_count(map_name)
        await analysis_cmd.finish(f"📊 「{map_name}」查询次数：{count} 次")
    else:
        top_maps = get_query_count()
        if not top_maps:
            await analysis_cmd.finish("📊 暂无查询记录！")

        msg = "📊 地图查询排行（前10）：\n"
        for idx, (name, count) in enumerate(top_maps[:10], 1):
            msg += f"{idx}. {name}：{count} 次\n"
        await analysis_cmd.finish(msg.strip())


# ====================== 7. 插件启动提示 ======================
@get_driver().on_startup
async def startup():
    print("✅ 地图查询插件加载完成（极简兼容版）")