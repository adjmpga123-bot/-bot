import os
import sqlite3
import discord

from discord.ext import commands
from discord import app_commands


# =========================================================
# 設定
# =========================================================

TOKEN = os.getenv("DISCORD_TOKEN")

# スタッフ用ロールID
# 自分のDiscordサーバーのスタッフロールIDに変更してください
STAFF_ROLE_ID = 0

# チケットを作成するカテゴリID
# 0なら自動的にカテゴリを作成します
TICKET_CATEGORY_ID = 0

# レビューを送るチャンネルID
# 0ならチケット内にのみ保存します
REVIEW_CHANNEL_ID = 0


# =========================================================
# Database
# =========================================================

db = sqlite3.connect("bot_data.db")
cursor = db.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS tickets (
    channel_id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    ticket_type TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    closed INTEGER DEFAULT 0
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_channel_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    rating INTEGER NOT NULL,
    comment TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
)
""")

db.commit()


# =========================================================
# Bot
# =========================================================

intents = discord.Intents.default()
intents.guilds = True
intents.members = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


# =========================================================
# 共通関数
# =========================================================

def is_staff(member: discord.Member):

    if member.guild_permissions.administrator:
        return True

    if STAFF_ROLE_ID == 0:
        return False

    return any(role.id == STAFF_ROLE_ID for role in member.roles)


def get_ticket(channel_id):

    cursor.execute(
        "SELECT * FROM tickets WHERE channel_id = ?",
        (channel_id,)
    )

    return cursor.fetchone()


async def get_or_create_category(guild):

    if TICKET_CATEGORY_ID != 0:

        category = guild.get_channel(TICKET_CATEGORY_ID)

        if isinstance(category, discord.CategoryChannel):
            return category

    category = discord.utils.get(
        guild.categories,
        name="🎫｜依頼チケット"
    )

    if category:
        return category

    category = await guild.create_category(
        "🎫｜依頼チケット"
    )

    return category


# =========================================================
# Bot Ready
# =========================================================

@bot.event
async def on_ready():

    print("--------------------------------")
    print(f"ログイン成功: {bot.user}")
    print(f"ID: {bot.user.id}")
    print("--------------------------------")

    try:

        synced = await bot.tree.sync()

        print(f"Slash Command同期: {len(synced)}個")

    except Exception as e:

        print("Slash Command同期エラー")
        print(e)


# =========================================================
# 依頼フォーム
# =========================================================

class RequestModal(discord.ui.Modal):

    def __init__(self, request_type):

        super().__init__(
            title=f"{request_type}依頼"
        )

        self.request_type = request_type

        self.name = discord.ui.TextInput(
            label="依頼名",
            placeholder="例：カピころBot制作",
            required=True,
            max_length=100
        )

        self.details = discord.ui.TextInput(
            label="依頼内容",
            placeholder="作ってほしいもの・必要な機能など",
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=1500
        )

        self.budget = discord.ui.TextInput(
            label="予算",
            placeholder="例：5000円 / 要相談",
            required=False,
            max_length=100
        )

        self.deadline = discord.ui.TextInput(
            label="希望納期",
            placeholder="例：1週間以内 / 特になし",
            required=False,
            max_length=100
        )

        self.other = discord.ui.TextInput(
            label="その他",
            placeholder="その他伝えておきたいこと",
            style=discord.TextStyle.paragraph,
            required=False,
            max_length=1000
        )

        self.add_item(self.name)
        self.add_item(self.details)
        self.add_item(self.budget)
        self.add_item(self.deadline)
        self.add_item(self.other)

    async def on_submit(self, interaction: discord.Interaction):

        guild = interaction.guild

        if guild is None:

            await interaction.response.send_message(
                "サーバー内で使用してください。",
                ephemeral=True
            )

            return

        await interaction.response.defer(
            ephemeral=True
        )

        category = await get_or_create_category(guild)

        # 同じユーザーの開いているチケットを確認

        cursor.execute(
            """
            SELECT channel_id
            FROM tickets
            WHERE user_id = ? AND closed = 0
            """,
            (interaction.user.id,)
        )

        existing = cursor.fetchone()

        if existing:

            channel = guild.get_channel(existing[0])

            if channel:

                await interaction.followup.send(
                    f"すでに依頼チケットがあります。\n{channel.mention}",
                    ephemeral=True
                )

                return

        # チャンネル名

        safe_name = (
            self.name.value
            .lower()
            .replace(" ", "-")
        )

        channel_name = f"ticket-{interaction.user.name}-{safe_name}"

        overwrites = {

            guild.default_role:
                discord.PermissionOverwrite(
                    view_channel=False
                ),

            interaction.user:
                discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True
                ),

            guild.me:
                discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    manage_channels=True,
                    read_message_history=True
                )
        }

        # スタッフロール

        if STAFF_ROLE_ID != 0:

            staff_role = guild.get_role(
                STAFF_ROLE_ID
            )

            if staff_role:

                overwrites[staff_role] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True
                )

        channel = await guild.create_text_channel(
            channel_name[:100],
            category=category,
            overwrites=overwrites,
            topic=f"{self.request_type} | {interaction.user.id}"
        )

        # DB保存

        cursor.execute(
            """
            INSERT INTO tickets
            (channel_id, user_id, ticket_type)
            VALUES (?, ?, ?)
            """,
            (
                channel.id,
                interaction.user.id,
                self.request_type
            )
        )

        db.commit()

        # Embed

        embed = discord.Embed(
            title="🎫 新規依頼",
            description=(
                "依頼を受け付けました。\n"
                "スタッフが内容を確認します。"
            ),
            color=discord.Color.blurple()
        )

        embed.add_field(
            name="📌 種類",
            value=self.request_type,
            inline=False
        )

        embed.add_field(
            name="📋 依頼名",
            value=self.name.value,
            inline=False
        )

        embed.add_field(
            name="📝 内容",
            value=self.details.value,
            inline=False
        )

        embed.add_field(
            name="💰 予算",
            value=self.budget.value or "未記入",
            inline=True
        )

        embed.add_field(
            name="⏰ 希望納期",
            value=self.deadline.value or "未記入",
            inline=True
        )

        embed.add_field(
            name="📎 その他",
            value=self.other.value or "なし",
            inline=False
        )

        embed.set_footer(
            text=f"依頼者: {interaction.user}"
        )

        await channel.send(
            content=(
                f"{interaction.user.mention}\n"
                "スタッフが対応します。"
            ),
            embed=embed,
            view=TicketControlView()
        )

        await interaction.followup.send(
            f"✅ 依頼チケットを作成しました。\n{channel.mention}",
            ephemeral=True
        )


# =========================================================
# 依頼選択View
# =========================================================

class RequestSelect(discord.ui.Select):

    def __init__(self):

        options = [

            discord.SelectOption(
                label="Bot作成依頼",
                value="🤖 Bot作成",
                emoji="🤖",
                description="Discord Botの制作を依頼"
            ),

            discord.SelectOption(
                label="鯖作成・構築依頼",
                value="🏠 鯖作成・構築",
                emoji="🏠",
                description="Discordサーバーの作成・構築"
            ),

            discord.SelectOption(
                label="Bot導入・設定",
                value="🔧 Bot導入・設定",
                emoji="🔧",
                description="Botの導入・設定を依頼"
            ),

            discord.SelectOption(
                label="デザイン依頼",
                value="🎨 デザイン",
                emoji="🎨",
                description="アイコン・バナーなど"
            ),

            discord.SelectOption(
                label="その他",
                value="🛠️ その他",
                emoji="🛠️",
                description="その他の依頼"
            )
        ]

        super().__init__(
            placeholder="依頼内容を選択してください",
            options=options,
            custom_id="request_select"
        )

    async def callback(self, interaction):

        await interaction.response.send_modal(
            RequestModal(self.values[0])
        )


class RequestPanelView(discord.ui.View):

    def __init__(self):

        super().__init__(
            timeout=None
        )

        self.add_item(
            RequestSelect()
        )


# =========================================================
# チケット操作
# =========================================================

class TicketControlView(discord.ui.View):

    def __init__(self):

        super().__init__(
            timeout=None
        )

    @discord.ui.button(
        label="チケットを閉じる",
        emoji="🔒",
        style=discord.ButtonStyle.danger,
        custom_id="close_ticket"
    )
    async def close_ticket(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        ticket = get_ticket(
            interaction.channel.id
        )

        if not ticket:

            await interaction.response.send_message(
                "このチャンネルは依頼チケットとして登録されていません。",
                ephemeral=True
            )

            return

        owner_id = ticket[1]

        if (
            interaction.user.id != owner_id
            and not is_staff(interaction.user)
        ):

            await interaction.response.send_message(
                "この操作を行う権限がありません。",
                ephemeral=True
            )

            return

        await interaction.response.send_message(
            "🔒 チケットをクローズします..."
        )

        # DB更新

        cursor.execute(
            """
            UPDATE tickets
            SET closed = 1
            WHERE channel_id = ?
            """,
            (interaction.channel.id,)
        )

        db.commit()

        # チャンネル名変更

        try:

            await interaction.channel.edit(
                name=f"closed-{interaction.channel.name}"[:100]
            )

        except:
            pass

        # ユーザーの書き込み権限を削除

        member = interaction.guild.get_member(
            owner_id
        )

        if member:

            await interaction.channel.set_permissions(
                member,
                send_messages=False
            )

        review_view = ReviewView(
            owner_id,
            interaction.channel.id
        )

        await interaction.channel.send(
            "🔒 **この依頼はクローズされました。**\n\n"
            "対応が完了していましたら、下のボタンからレビューできます。",
            view=review_view
        )


# =========================================================
# レビュー
# =========================================================

class ReviewModal(discord.ui.Modal):

    def __init__(
        self,
        owner_id,
        ticket_channel_id,
        rating
    ):

        super().__init__(
            title="レビュー"
        )

        self.owner_id = owner_id
        self.ticket_channel_id = ticket_channel_id
        self.rating = rating

        self.comment = discord.ui.TextInput(
            label="コメント",
            placeholder="対応についてコメントしてください",
            style=discord.TextStyle.paragraph,
            required=False,
            max_length=1000
        )

        self.add_item(
            self.comment
        )

    async def on_submit(
        self,
        interaction: discord.Interaction
    ):

        if interaction.user.id != self.owner_id:

            await interaction.response.send_message(
                "このレビューは依頼者本人のみ送信できます。",
                ephemeral=True
            )

            return

        # 既にレビュー済みか

        cursor.execute(
            """
            SELECT id
            FROM reviews
            WHERE ticket_channel_id = ?
            """,
            (self.ticket_channel_id,)
        )

        if cursor.fetchone():

            await interaction.response.send_message(
                "この依頼はすでにレビュー済みです。",
                ephemeral=True
            )

            return

        cursor.execute(
            """
            INSERT INTO reviews
            (ticket_channel_id, user_id, rating, comment)
            VALUES (?, ?, ?, ?)
            """,
            (
                self.ticket_channel_id,
                interaction.user.id,
                self.rating,
                self.comment.value
            )
        )

        db.commit()

        # レビュー通知

        review_channel = None

        if REVIEW_CHANNEL_ID != 0:

            review_channel = interaction.guild.get_channel(
                REVIEW_CHANNEL_ID
            )

        if review_channel:

            stars = "⭐" * self.rating

            embed = discord.Embed(
                title="⭐ 新しいレビュー",
                color=discord.Color.gold()
            )

            embed.add_field(
                name="評価",
                value=stars,
                inline=False
            )

            embed.add_field(
                name="コメント",
                value=self.comment.value or "なし",
                inline=False
            )

            embed.add_field(
                name="依頼者",
                value=interaction.user.mention,
                inline=False
            )

            await review_channel.send(
                embed=embed
            )

        await interaction.response.send_message(
            "⭐ レビューを送信しました！\n"
            "ご依頼ありがとうございました。",
            ephemeral=True
        )


class ReviewView(discord.ui.View):

    def __init__(
        self,
        owner_id,
        ticket_channel_id
    ):

        super().__init__(
            timeout=None
        )

        self.owner_id = owner_id
        self.ticket_channel_id = ticket_channel_id

    async def review(
        self,
        interaction,
        rating
    ):

        if interaction.user.id != self.owner_id:

            await interaction.response.send_message(
                "依頼者本人のみレビューできます。",
                ephemeral=True
            )

            return

        await interaction.response.send_modal(
            ReviewModal(
                self.owner_id,
                self.ticket_channel_id,
                rating
            )
        )

    @discord.ui.button(
        label="1",
        emoji="⭐",
        style=discord.ButtonStyle.secondary,
        custom_id="review_1"
    )
    async def one(self, interaction, button):

        await self.review(
            interaction,
            1
        )

    @discord.ui.button(
        label="2",
        emoji="⭐",
        style=discord.ButtonStyle.secondary,
        custom_id="review_2"
    )
    async def two(self, interaction, button):

        await self.review(
            interaction,
            2
        )

    @discord.ui.button(
        label="3",
        emoji="⭐",
        style=discord.ButtonStyle.secondary,
        custom_id="review_3"
    )
    async def three(self, interaction, button):

        await self.review(
            interaction,
            3
        )

    @discord.ui.button(
        label="4",
        emoji="⭐",
        style=discord.ButtonStyle.primary,
        custom_id="review_4"
    )
    async def four(self, interaction, button):

        await self.review(
            interaction,
            4
        )

    @discord.ui.button(
        label="5",
        emoji="⭐",
        style=discord.ButtonStyle.success,
        custom_id="review_5"
    )
    async def five(self, interaction, button):

        await self.review(
            interaction,
            5
        )


# =========================================================
# /setup
# =========================================================

@bot.tree.command(
    name="setup",
    description="依頼受付パネルを設置します"
)
@app_commands.default_permissions(
    administrator=True
)
async def setup(
    interaction: discord.Interaction
):

    embed = discord.Embed(
        title="📋 依頼受付センター",
        description=(
            "ご依頼はこちらから受け付けています。\n\n"

            "🤖 **Bot作成依頼**\n"
            "Discord Botの制作\n\n"

            "🏠 **鯖作成・構築依頼**\n"
            "Discordサーバーの作成・構築\n\n"

            "🔧 **Bot導入・設定**\n"
            "Botの導入・各種設定\n\n"

            "🎨 **デザイン依頼**\n"
            "アイコン・バナーなど\n\n"

            "🛠️ **その他**\n"
            "上記以外のご依頼\n\n"

            "下のメニューから依頼内容を選択してください。"
        ),
        color=discord.Color.blurple()
    )

    embed.set_footer(
        text="依頼後、専用チケットが自動作成されます。"
    )

    await interaction.channel.send(
        embed=embed,
        view=RequestPanelView()
    )

    await interaction.response.send_message(
        "✅ 依頼パネルを設置しました。",
        ephemeral=True
    )


# =========================================================
# /ticket
# =========================================================

@bot.tree.command(
    name="ticket",
    description="自分の依頼チケットを確認します"
)
async def ticket(
    interaction: discord.Interaction
):

    cursor.execute(
        """
        SELECT channel_id, ticket_type, closed
        FROM tickets
        WHERE user_id = ?
        ORDER BY created_at DESC
        """,
        (interaction.user.id,)
    )

    rows = cursor.fetchall()

    if not rows:

        await interaction.response.send_message(
            "依頼履歴はありません。",
            ephemeral=True
        )

        return

    text = ""

    for channel_id, ticket_type, closed in rows[:10]:

        channel = interaction.guild.get_channel(
            channel_id
        )

        status = "🔒 完了" if closed else "🟢 対応中"

        if channel:

            text += (
                f"{status} {ticket_type} "
                f"{channel.mention}\n"
            )

        else:

            text += (
                f"{status} {ticket_type} "
                f"`削除済み`\n"
            )

    embed = discord.Embed(
        title="🎫 あなたの依頼",
        description=text,
        color=discord.Color.blurple()
    )

    await interaction.response.send_message(
        embed=embed,
        ephemeral=True
    )


# =========================================================
# /reviews
# =========================================================

@bot.tree.command(
    name="reviews",
    description="レビュー統計を確認します"
)
async def reviews(
    interaction: discord.Interaction
):

    cursor.execute(
        """
        SELECT COUNT(*), AVG(rating)
        FROM reviews
        """
    )

    count, average = cursor.fetchone()

    if count == 0:

        await interaction.response.send_message(
            "まだレビューはありません。",
            ephemeral=True
        )

        return

    embed = discord.Embed(
        title="⭐ レビュー統計",
        color=discord.Color.gold()
    )

    embed.add_field(
        name="レビュー数",
        value=str(count),
        inline=True
    )

    embed.add_field(
        name="平均評価",
        value=f"{average:.2f} / 5",
        inline=True
    )

    await interaction.response.send_message(
        embed=embed
    )


# =========================================================
# /close
# =========================================================

@bot.tree.command(
    name="close",
    description="現在のチケットを閉じます"
)
async def close(
    interaction: discord.Interaction
):

    ticket = get_ticket(
        interaction.channel.id
    )

    if not ticket:

        await interaction.response.send_message(
            "ここはチケットではありません。",
            ephemeral=True
        )

        return

    if not is_staff(interaction.user):

        await interaction.response.send_message(
            "スタッフのみ使用できます。",
            ephemeral=True
        )

        return

    cursor.execute(
        """
        UPDATE tickets
        SET closed = 1
        WHERE channel_id = ?
        """,
        (interaction.channel.id,)
    )

    db.commit()

    await interaction.response.send_message(
        "🔒 チケットをクローズしました。"
    )


# =========================================================
# Bot起動
# =========================================================

if not TOKEN:

    print(
        "ERROR: DISCORD_TOKEN が設定されていません。"
    )

else:

    bot.run(TOKEN)