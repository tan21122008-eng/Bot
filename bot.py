from flask import Flask

import threading

app = Flask(__name__)

@app.route("/")

def home():

    return "Bot đang chạy!"

def run_web():

    app.run(host="0.0.0.0", port=10000)

threading.Thread(target=run_web).start()

import os
import sys
import math
import difflib
import asyncio
import logging
import aiohttp
import discord
from discord.ext import commands, tasks

# ─── Đảm bảo chỉ chạy 1 instance duy nhất ───────────────────────────────────
_PID_FILE = "/tmp/aotrbot.pid"
if os.path.exists(_PID_FILE):
    try:
        old_pid = int(open(_PID_FILE).read().strip())
        os.kill(old_pid, 9)
    except (ProcessLookupError, ValueError):
        pass
with open(_PID_FILE, "w") as _f:
    _f.write(str(os.getpid()))

SUPABASE_URL = "https://kcxzghpcfobpnlvlvtib.supabase.co"
SUPABASE_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    ".eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImtjeHpnaHBjZm9icG5sdmx2dGliIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTE1NjQ5ODgsImV4cCI6MjA2NzE0MDk4OH0"
    ".frunhRobCUlKGCz1IgnuXtoGyMBUKwQQ3xQc_iFyEMg"
)
SITE_BASE = "https://www.aotrvalue.com"
VIZ_TO_SCROLLS = 300

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

item_cache: list[dict] = []


# ─── Lấy dữ liệu từ Supabase ─────────────────────────────────────────────────


async def fetch_all_items() -> list[dict]:
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
    }
    all_items: list[dict] = []
    page_size = 1000
    offset = 0
    async with aiohttp.ClientSession() as session:
        while True:
            url = (
                f"{SUPABASE_URL}/rest/v1/items"
                f"?select=id,name,value,demand,rate_of_change,prestige,status,"
                f"obtained_from,gem_tax,gold_tax,category,rarity,emoji"
                f"&order=value.desc"
                f"&limit={page_size}&offset={offset}"
            )
            async with session.get(url, headers=headers) as resp:
                data = await resp.json()
                if not isinstance(data, list) or not data:
                    break
                all_items.extend(data)
                if len(data) < page_size:
                    break
                offset += page_size
    return all_items


# ─── Tiện ích định dạng ───────────────────────────────────────────────────────


def fmt_viz(value: float) -> str:
    if value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.2f}B"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.2f}M"
    if value >= 1_000:
        return f"{value / 1_000:.1f}K"
    return f"{value:,.2f}"


def fmt_scrolls(scrolls: float) -> str:
    if scrolls >= 1_000_000:
        return f"{scrolls / 1_000_000:.2f}M"
    if scrolls >= 1_000:
        return f"{scrolls / 1_000:.1f}K"
    return f"{int(scrolls):,}"


def demand_bar(demand) -> str:
    d = int(demand or 0)
    return "█" * d + "░" * (10 - d) + f"  {d}/10"


def get_thumbnail(item: dict) -> str | None:
    emoji = (item.get("emoji") or "").strip()
    if not emoji:
        return None
    if emoji.startswith("http"):
        return emoji
    if emoji.startswith("/"):
        return f"{SITE_BASE}{emoji}"
    return None


def find_item(query: str) -> dict | None:
    q = query.lower().strip()
    for item in item_cache:
        if item["name"].lower() == q:
            return item
    names = [item["name"].lower() for item in item_cache]
    matches = difflib.get_close_matches(q, names, n=1, cutoff=0.35)
    if matches:
        for item in item_cache:
            if item["name"].lower() == matches[0]:
                return item
    return None


def search_items(query: str, limit: int = 20) -> list[dict]:
    q = query.lower().strip()
    exact = [i for i in item_cache if q in i["name"].lower()]
    if exact:
        return exact[:limit]
    names = [i["name"].lower() for i in item_cache]
    fuzzy = difflib.get_close_matches(q, names, n=limit, cutoff=0.3)
    return [i for i in item_cache if i["name"].lower() in fuzzy]


# ─── Tạo Embed duy nhất ───────────────────────────────────────────────────────

ROC_VI = {
    "Rising": "📈 Đang Tăng",
    "Falling": "📉 Đang Giảm",
    "Stable": "➡️ Ổn Định",
    "Overpriced": "⚠️ Quá Giá",
}
ROC_COLOR = {
    "Rising": 0x2ECC71,
    "Falling": 0xE74C3C,
    "Stable": 0xF1C40F,
    "Overpriced": 0xE67E22,
}


def build_embed(item: dict) -> discord.Embed:
    viz = float(item["value"])
    scrolls = viz * VIZ_TO_SCROLLS
    roc = item.get("rate_of_change") or "Stable"

    embed = discord.Embed(
        title=f"⚔️  {item['name']}",
        color=ROC_COLOR.get(roc, 0xC4A04A),
    )

    # Thumbnail
    thumb = get_thumbnail(item)
    if thumb:
        embed.set_thumbnail(url=thumb)

    # ── Table: core stats ─────────────────────────────
    tax_label = ""
    if item.get("gem_tax"):
        tax_label = f"{item['gem_tax']:,} 💜"
    elif item.get("gold_tax"):
        tax_label = f"{item['gold_tax']:,} 🟡"

    obtained = (item.get("obtained_from") or "").strip()
    category  = item.get("category") or "—"

    rows = [
        ("💎 Giá Viz",   f"`{fmt_viz(viz)}`"),
        ("📜 Số Scroll", f"`{fmt_scrolls(scrolls)}`"),
        ("🔥 Độ Hot",    f"`{demand_bar(item.get('demand'))}`"),
        ("➡️ Xu Hướng",  ROC_VI.get(roc, roc)),
        ("📦 Phân Loại", category),
    ]
    if obtained:
        rows.append(("🎁 Cách Sở Hữu", obtained))
    if tax_label:
        rows.append(("💸 Thuế", tax_label))

    embed.description = "\n".join(f"**{k}** — {v}" for k, v in rows)

    return embed


def build_error_embed(message: str) -> discord.Embed:
    """Tạo embed lỗi duy nhất"""
    return discord.Embed(description=f"❌ {message}", color=0xE74C3C)


def build_warning_embed(message: str) -> discord.Embed:
    """Tạo embed cảnh báo duy nhất"""
    return discord.Embed(description=message, color=0xF1C40F)


def build_info_embed(title: str, description: str = "", color: int = 0xC4A04A) -> discord.Embed:
    """Tạo embed thông tin duy nhất"""
    embed = discord.Embed(title=title, color=color)
    if description:
        embed.description = description
    return embed


# ─── Sự kiện bot ─────────────────────────────────────────────────────────────


@bot.event
async def on_ready():
    global item_cache
    print("========================================")
    print(f"✅ Bot {bot.user.name if bot.user else 'Bot'} online — đang tải dữ liệu…")
    item_cache = await fetch_all_items()
    print(f"✅ Đã tải {len(item_cache)} vật phẩm từ aotrvalue.com")
    print("========================================")
    await bot.change_presence(activity=discord.Game(name="!check [vật phẩm] | !values"))
    if not refresh_cache.is_running():
        refresh_cache.start()


@tasks.loop(minutes=30)
async def refresh_cache():
    global item_cache
    updated = await fetch_all_items()
    if updated:
        item_cache = updated
        print(f"[cache] Đã cập nhật — {len(item_cache)} vật phẩm")


# ─── Lệnh tra giá ────────────────────────────────────────────────────────────


@bot.command(name="gia", aliases=["kiemtra", "check", "price", "value"])
async def check_item(ctx, *, item_name: str | None = None):
    if not item_name:
        await ctx.send(embed=build_error_embed("Bạn chưa nhập tên vật phẩm!\n👉 Ví dụ: `!gia Attack Serum`"))
        return

    item = find_item(item_name)
    if not item:
        await ctx.send(embed=build_error_embed(f"Không tìm thấy **{item_name}**.\n💡 Dùng `!banggia` để duyệt toàn bộ {len(item_cache)} vật phẩm."))
        return

    await ctx.send(embed=build_embed(item))


@bot.command(name="timkiem", aliases=["search", "tim"])
async def cmd_search(ctx, *, query: str | None = None):
    if not query:
        await ctx.send(embed=build_error_embed("Bạn chưa nhập từ khoá!\n👉 Ví dụ: `!timkiem Serum`"))
        return

    results = search_items(query)
    if not results:
        await ctx.send(embed=build_error_embed(f"Không tìm thấy vật phẩm nào khớp với **{query}**."))
        return

    lines = []
    for i, item in enumerate(results, 1):
        viz = float(item["value"])
        scrolls = viz * VIZ_TO_SCROLLS
        roc = item.get("rate_of_change") or ""
        icon = {"Rising": "📈", "Falling": "📉", "Overpriced": "⚠️"}.get(roc, "➡️")
        lines.append(
            f"`{i:>2}.` {icon} **{item['name']}**\n"
            f"      💎 {fmt_viz(viz)} viz  •  📜 {fmt_scrolls(scrolls)} scroll"
        )

    embed = build_info_embed(title=f"🔍  Kết Quả: \"{query}\"  ({len(results)} vật phẩm)")
    embed.description = "\n".join(lines)
    await ctx.send(embed=embed)


# ─── Bảng giá toàn bộ (có nút lật trang) ────────────────────────────────────


class ValuesView(discord.ui.View):
    PAGE_SIZE = 20

    def __init__(self, items: list[dict], author_id: int, title: str = ""):
        super().__init__(timeout=120)
        self.items = items
        self.author_id = author_id
        self.title = title or f"📋  Bảng Giá AOTR  ({len(items)} vật phẩm)"
        self.page = 0
        self.total_pages = math.ceil(len(items) / self.PAGE_SIZE)
        self._sync_buttons()

    def _sync_buttons(self):
        self.prev_btn.disabled = self.page == 0
        self.next_btn.disabled = self.page >= self.total_pages - 1
        self.page_label.label = f"Trang {self.page + 1}/{self.total_pages}"

    def make_embed(self) -> discord.Embed:
        start = self.page * self.PAGE_SIZE
        chunk = self.items[start : start + self.PAGE_SIZE]
        embed = discord.Embed(title=self.title, color=0xC4A04A)
        lines = []
        for i, item in enumerate(chunk, start=start + 1):
            viz = float(item["value"])
            scrolls = viz * VIZ_TO_SCROLLS
            roc = item.get("rate_of_change") or ""
            icon = {"Rising": "📈", "Falling": "📉", "Overpriced": "⚠️"}.get(roc, "➡️")
            lines.append(
                f"`{i:>3}.` {icon} **{item['name']}**\n"
                f"       💎 {fmt_viz(viz)} viz  •  📜 {fmt_scrolls(scrolls)} scroll"
            )
        embed.description = "\n".join(lines)
        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "❌ Chỉ người dùng lệnh mới có thể lật trang.", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="◀ Trước", style=discord.ButtonStyle.secondary)
    async def prev_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        self.page -= 1
        self._sync_buttons()
        await interaction.response.edit_message(embed=self.make_embed(), view=self)

    @discord.ui.button(
        label="Trang 1/1", style=discord.ButtonStyle.primary, disabled=True
    )
    async def page_label(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        pass

    @discord.ui.button(label="Tiếp ▶", style=discord.ButtonStyle.secondary)
    async def next_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        self.page += 1
        self._sync_buttons()
        await interaction.response.edit_message(embed=self.make_embed(), view=self)


@bot.command(name="banggia", aliases=["danhsach", "vatpham", "values", "list"])
async def cmd_values(ctx, *, category: str | None = None):
    if not item_cache:
        await ctx.send(embed=build_warning_embed("⏳ Đang tải dữ liệu, vui lòng thử lại sau giây lát."))
        return

    items = item_cache
    title = ""
    if category:
        items = [i for i in items if (i.get("category") or "").lower() == category.lower()]
        if not items:
            await ctx.send(embed=build_error_embed(f"Không tìm thấy phân loại **{category}**.\n📂 Gõ `!phanloai` để xem danh sách."))
            return
        title = f"📦  {category}  ({len(items)} vật phẩm)"

    view = ValuesView(items, ctx.author.id, title=title)
    await ctx.send(embed=view.make_embed(), view=view)


@bot.command(name="phanloai", aliases=["loai", "categories", "cats"])
async def cmd_categories(ctx):
    cats = sorted({i.get("category") for i in item_cache if i.get("category")})
    embed = build_info_embed(title="📂  Danh Sách Phân Loại")
    embed.description = "\n".join(f"• **{c}**" for c in cats)
    await ctx.send(embed=embed)


@bot.command(name="top", aliases=["xephang"])
async def cmd_top(ctx, count: int = 10):
    count = min(max(count, 1), 25)
    embed = build_info_embed(
        title=f"🏆  Top {count} Vật Phẩm Giá Trị Nhất",
        color=0xFFD700,
    )
    lines = []
    for i, item in enumerate(item_cache[:count], 1):
        viz = float(item["value"])
        lines.append(
            f"`#{i:>2}` **{item['name']}** — "
            f"{fmt_viz(viz)} viz / {fmt_scrolls(viz * VIZ_TO_SCROLLS)} scroll"
        )
    embed.description = "\n".join(lines)
    await ctx.send(embed=embed)


@bot.command(name="huongdan", aliases=["lenh", "trogiup", "aotr", "help"])
async def cmd_help(ctx):
    embed = build_info_embed(
        title="⚔️  AOTR Value Bot — Hướng Dẫn",
        description="Bot tra giá vật phẩm Attack on Titan Revolution",
    )
    embed.add_field(
        name="🔍  !gia <tên vật phẩm>",
        value="Xem giá Viz & số Scroll của vật phẩm.\nAlias: `!kiemtra` `!check`",
        inline=False,
    )
    embed.add_field(
        name="🔎  !timkiem <từ khoá>",
        value="Tìm nhiều vật phẩm khớp với từ khoá.\nAlias: `!tim` `!search`",
        inline=False,
    )
    embed.add_field(
        name="📋  !banggia [phân loại]",
        value="Duyệt toàn bộ bảng giá, có nút lật trang.\nAlias: `!danhsach` `!vatpham`",
        inline=False,
    )
    embed.add_field(
        name="📂  !phanloai",
        value="Xem danh sách tất cả phân loại.\nAlias: `!loai`",
        inline=False,
    )
    embed.add_field(
        name="🏆  !top [số]",
        value="Top N vật phẩm giá trị nhất (mặc định 10, tối đa 25).\nAlias: `!xephang`",
        inline=False,
    )
    embed.add_field(
        name="💱  Tỷ lệ",
        value=f"`1 Viz = {VIZ_TO_SCROLLS} Scrolls` — dữ liệu tự cập nhật mỗi 30 phút.",
        inline=False,
    )
    await ctx.send(embed=embed)


# ─── Khởi động ────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# ⭐ THAY DÒNG NÀY BẰNG TOKEN CỦA BẠN
DISCORD_BOT_TOKEN = "MTUxMDcwODY4NjMzNzYwNTcxNA.GXdB3E.g0ueyENEAooBJEzSqjuV_tG8NrkF3jXo1fouu4"  # ← Thay token vào đây

token = os.environ.get("DISCORD_BOT_TOKEN") or DISCORD_BOT_TOKEN

if not token or token == "MTUxMDcwODY4NjMzNzYwNTcxNA.GXdB3E.g0ueyENEAooBJEzSqjuV_tG8NrkF3jXo1fouu4":
    logging.critical("❌ DISCORD_BOT_TOKEN chưa được thiết lập. Bot dừng lại.")
    sys.exit(1)

try:
    print("🚀 Bot đang khởi động...")
    bot.run(token)
except discord.LoginFailure:
    logging.critical("❌ Token không hợp lệ. Kiểm tra lại DISCORD_BOT_TOKEN.")
    sys.exit(1)
except Exception as e:
    logging.critical(f"❌ Bot dừng do lỗi không xử lý được: {e}", exc_info=True)
    sys.exit(1)
