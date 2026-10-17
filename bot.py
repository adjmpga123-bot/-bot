import os
import sqlite3
import discord

from discord.ext import commands
from discord import app_commands


# =========================================================
# 設定
# =========================================================

TOKEN = os.getenv("DISCORD_TOKEN")

# スタッフロールID
# 例: STAFF_ROLE_ID = 123456789012345678
STAFF_ROLE_ID = 0

# チケットカテゴリID
# 0の場合は「🎫｜依頼チケット」を自動作成
TICKET_CATEGORY_ID = 0

# レビューを送るチャンネルID
# 0の場合はレビュー通知なし
REVIEW_CHANNEL_ID = 0


# =========================================================
# データベース
# =========================================================

db = sqlite3.connect("bot_data.db")
cursor = db.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS tickets (
    channel_id INTEGER PRIMARY KEY,
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    ticket_type TEXT NOT NULL,
    request_name TEXT NOT NULL,
    details TEXT NOT NULL,
    budget TEXT,
    deadline TEXT,
    other TEXT,
    status TEXT DEFAULT '受付',
    staff_id INTEGER DEFAULT 0,
    quote TEXT DEFAULT '',
    delivery TEXT DEFAULT '',
    closed INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_channel_id INTEGER NOT NULL,
    guild_id INTEGER NOT NULL,
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

    role = member.guild.get_role(STAFF_ROLE_ID)

    if role is None:
        return False

    return role in member.roles


def get_ticket(channel_id):

    cursor.execute(
        """
        SELECT *
        FROM tickets
        WHERE channel_id = ?
        """,
        (channel_id,)
    )

    return cursor.fetchone()


def get_status_emoji(status):

    emojis = {
        "受付": "🟡",
        "確認中": "🔵",
        "作業中": "🟠",
        "テスト中": "🟣",
        "納品済み": "🟢",
        "完了": "✅",
        "キャンセル": "❌"
    }

    return emojis.get(status, "⚪")


async def get_ticket_category(guild):

    # 指定カテゴリを使用

    if TICKET_CATEGORY_ID != 0:

        category = guild.get_channel(
            TICKET_CATEGORY_ID
        )

        if isinstance(
            category,
            discord.CategoryChannel
        ):
            return category

    # 自動作成したカテゴリを探す

    category = discord.utils.get(
        guild.categories,
        name="🎫｜依頼チケット"
    )

    if category:
        return category

    # なければ作成

    return await guild.create_category(
        "🎫｜依頼チケット"
    )


async def update_ticket_embed(channel):

    ticket = get_ticket(channel.id)

    if not ticket:
        return

    (
        channel_id,
        guild_id,
        user_id,
        ticket_type,
        request_name,
        details,
        budget,
        deadline,
        other,
        status,
        staff_id,
        quote,
        delivery,
        closed,
        created_at
    ) = ticket

    guild = channel.guild

    user = guild.get_member(user_id)

    staff_text = "未担当"

    if staff_id:

        staff = guild.get_member(staff_id)

        if staff:
            staff_text = staff.mention
        else:
            staff_text = f"<@{staff_id}>"

    embed = discord.Embed(
        title=f"🎫 依頼 #{channel.id}",
        color=discord.Color.blurple()
    )

    embed.add_field(
        name="📌 種類",
        value=ticket_type,
        inline=False
    )

    embed.add_field(
        name="📝 依頼名",
        value=request_name,
        inline=False
    )

    embed.add_field(
        name="📊 ステータス",
        value=f"{get_status_emoji(status)} {status}",
        inline=True
    )

    embed.add_field(
        name="👤 依頼者",
        value=user.mention if user else f"<@{user_id}>",
        inline=True
    )

    embed.add_field(
        name="👨‍💻 担当者",
        value=staff_text,
        inline=True
    )

    embed.add_field(
        name="💰 予算",
        value=budget or "未記入",
        inline=True
    )

    embed.add_field(
        name="💵 見積",
        value=quote or "未設定",
        inline=True
    )

    embed.add_field(
        name="⏰ 希望納期",
        value=deadline or "未記入",
        inline=True
    )

    embed.add_field(
        name="📋 内容",
        value=details[:1024],
        inline=False
    )

    if delivery:

        embed.add_field(
            name="📦 納品",
            value=delivery[:1024],
            inline=False
        )

    if other:

        embed.add_field(
            name="📎 その他",
            value=other[:1024],
            inline=False
        )

    embed.set_footer(
        text=f"作成日時: {created_at}"
    )

    return embed


# =========================================================
# Bot起動
# =========================================================

@bot.event
async def on_ready():

    print("==============================")
    print(f"ログイン: {bot.user}")
    print(f"Bot ID: {bot.user.id}")
    print("==============================")

    # 永続View

    bot.add_view(RequestPanelView())
    bot.add_view(TicketControlView())

    try:

        synced = await bot.tree.sync()

        print(
            f"Slash Command同期: {len(synced)}個"
        )

    except Exception as e:

        print(
            f"Slash Command同期エラー: {e}"
        )


# =========================================================
# 依頼フォーム
# =========================================================

class RequestModal(discord.ui.Modal):

    def __init__(self, request_type):

        super().__init__(
            title=f"{request_type}依頼"
        )

        self.request_type = request_type

        self.request_name = discord.ui.TextInput(
            label="依頼名",
            placeholder="例：多機能Discord Bot制作",
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

        self.add_item(self.request_name)
        self.add_item(self.details)
        self.add_item(self.budget)
        self.add_item(self.deadline)
        self.add_item(self.other)

    async def on_submit(
        self,
        interaction: discord.Interaction
    ):

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

        # 開いているチケットを確認

        cursor.execute(
            """
            SELECT channel_id
            FROM tickets
            WHERE guild_id = ?
            AND user_id = ?
            AND closed = 0
            """,
            (
                guild.id,
                interaction.user.id
            )
        )

        existing = cursor.fetchone()

        if existing:

            channel = guild.get_channel(
                existing[0]
            )

            if channel:

                await interaction.followup.send(
                    f"すでに依頼チケットがあります。\n"
                    f"{channel.mention}",
                    ephemeral=True
                )

                return

        # カテゴリ取得

        category = await get_ticket_category(
            guild
        )

        # チャンネル名

        channel_name = (
            f"ticket-{interaction.user.name}"
        )

        channel_name = channel_name[:90]

        # 権限

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
                    manage_permissions=True,
                    read_message_history=True
                )
        }

        # スタッフ

        if STAFF_ROLE_ID != 0:

            staff_role = guild.get_role(
                STAFF_ROLE_ID
            )

            if staff_role:

                overwrites[staff_role] = (
                    discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=True,
                        read_message_history=True
                    )
                )

        # チャンネル作成

        channel = await guild.create_text_channel(
            channel_name,
            category=category,
            overwrites=overwrites,
            topic=(
                f"{self.request_type} | "
                f"{interaction.user.id}"
            )
        )

        # DB登録

        cursor.execute(
            """
            INSERT INTO tickets
            (
                channel_id,
                guild_id,
                user_id,
                ticket_type,
                request_name,
                details,
                budget,
                deadline,
                other
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                channel.id,
                guild.id,
                interaction.user.id,
                self.request_type,
                self.request_name.value,
                self.details.value,
                self.budget.value,
                self.deadline.value,
                self.other.value
            )
        )

        db.commit()

        embed = await update_ticket_embed(
            channel
        )

        await channel.send(
            content=(
                f"{interaction.user.mention}\n"
                "📋 **依頼を受け付けました！**\n"
                "スタッフが内容を確認します。"
            ),
            embed=embed,
            view=TicketControlView()
        )

        await interaction.followup.send(
            "✅ 依頼チケットを作成しました。\n"
            f"{channel.mention}",
            ephemeral=True
        )


# =========================================================
# 依頼選択
# =========================================================

class RequestSelect(discord.ui.Select):

    def __init__(self):

        options = [

            discord.SelectOption(
                label="Bot作成依頼",
                value="🤖 Bot作成",
                emoji="🤖",
                description="Discord Botを新規制作"
            ),

            discord.SelectOption(
                label="鯖作成・構築依頼",
                value="🏠 鯖作成・構築",
                emoji="🏠",
                description="Discordサーバーを構築"
            ),

            discord.SelectOption(
                label="Bot導入・設定",
                value="🔧 Bot導入・設定",
                emoji="🔧",
                description="Botの導入・設定"
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
            RequestModal(
                self.values[0]
            )
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
# 担当者
# =========================================================

class AssignButton(
    discord.ui.Button
):

    def __init__(self):

        super().__init__(
            label="担当する",
            emoji="👤",
            style=discord.ButtonStyle.primary,
            custom_id="ticket_assign"
        )

    async def callback(self, interaction):

        if not is_staff(interaction.user):

            await interaction.response.send_message(
                "スタッフのみ使用できます。",
                ephemeral=True
            )

            return

        ticket = get_ticket(
            interaction.channel.id
        )

        if not ticket:

            await interaction.response.send_message(
                "チケット情報がありません。",
                ephemeral=True
            )

            return

        cursor.execute(
            """
            UPDATE tickets
            SET staff_id = ?
            WHERE channel_id = ?
            """,
            (
                interaction.user.id,
                interaction.channel.id
            )
        )

        db.commit()

        await interaction.response.send_message(
            f"👤 {interaction.user.mention} が担当になりました。"
        )

        embed = await update_ticket_embed(
            interaction.channel
        )

        # 最新Embedを送信

        await interaction.channel.send(
            embed=embed
        )


# =========================================================
# ステータス変更
# =========================================================

class StatusSelect(discord.ui.Select):

    def __init__(self):

        options = [

            discord.SelectOption(
                label="受付",
                value="受付",
                emoji="🟡"
            ),

            discord.SelectOption(
                label="確認中",
                value="確認中",
                emoji="🔵"
            ),

            discord.SelectOption(
                label="作業中",
                value="作業中",
                emoji="🟠"
            ),

            discord.SelectOption(
                label="テスト中",
                value="テスト中",
                emoji="🟣"
            ),

            discord.SelectOption(
                label="納品済み",
                value="納品済み",
                emoji="🟢"
            ),

            discord.SelectOption(
                label="完了",
                value="完了",
                emoji="✅"
            ),

            discord.SelectOption(
                label="キャンセル",
                value="キャンセル",
                emoji="❌"
            )
        ]

        super().__init__(
            placeholder="ステータスを変更",
            options=options,
            custom_id="ticket_status"
        )

    async def callback(self, interaction):

        if not is_staff(interaction.user):

            await interaction.response.send_message(
                "スタッフのみ使用できます。",
                ephemeral=True
            )

            return

        status = self.values[0]

        cursor.execute(
            """
            UPDATE tickets
            SET status = ?
            WHERE channel_id = ?
            """,
            (
                status,
                interaction.channel.id
            )
        )

        db.commit()

        await interaction.response.send_message(
            f"{get_status_emoji(status)} "
            f"ステータスを **{status}** に変更しました。"
        )

        embed = await update_ticket_embed(
            interaction.channel
        )

        await interaction.channel.send(
            embed=embed
        )


# =========================================================
# 見積もり
# =========================================================

class QuoteModal(discord.ui.Modal):

    def __init__(self):

        super().__init__(
            title="💰 見積もり設定"
        )

        self.quote = discord.ui.TextInput(
            label="見積金額",
            placeholder="例：5000円 / 要相談",
            required=True,
            max_length=100
        )

        self.add_item(
            self.quote
        )

    async def on_submit(self, interaction):

        if not is_staff(interaction.user):

            await interaction.response.send_message(
                "スタッフのみ使用できます。",
                ephemeral=True
            )

            return

        cursor.execute(
            """
            UPDATE tickets
            SET quote = ?
            WHERE channel_id = ?
            """,
            (
                self.quote.value,
                interaction.channel.id
            )
        )

        db.commit()

        await interaction.response.send_message(
            f"💰 見積もりを設定しました："
            f"**{self.quote.value}**"
        )


class QuoteButton(
    discord.ui.Button
):

    def __init__(self):

        super().__init__(
            label="見積もり",
            emoji="💰",
            style=discord.ButtonStyle.success,
            custom_id="ticket_quote"
        )

    async def callback(self, interaction):

        if not is_staff(interaction.user):

            await interaction.response.send_message(
                "スタッフのみ使用できます。",
                ephemeral=True
            )

            return

        await interaction.response.send_modal(
            QuoteModal()
        )


# =========================================================
# 納品
# =========================================================

class DeliveryModal(discord.ui.Modal):

    def __init__(self):

        super().__init__(
            title="📦 納品"
        )

        self.delivery = discord.ui.TextInput(
            label="納品内容",
            placeholder=(
                "納品内容・ファイルURL・説明など"
            ),
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=1500
        )

        self.add_item(
            self.delivery
        )

    async def on_submit(self, interaction):

        if not is_staff(interaction.user):

            await interaction.response.send_message(
                "スタッフのみ使用できます。",
                ephemeral=True
            )

            return

        cursor.execute(
            """
            UPDATE tickets
            SET delivery = ?,
                status = '納品済み'
            WHERE channel_id = ?
            """,
            (
                self.delivery.value,
                interaction.channel.id
            )
        )

        db.commit()

        await interaction.response.send_message(
            "📦 **納品しました！**\n"
            f"{self.delivery.value}"
        )

        embed = await update_ticket_embed(
            interaction.channel
        )

        await interaction.channel.send(
            embed=embed
        )


class DeliveryButton(
    discord.ui.Button
):

    def __init__(self):

        super().__init__(
            label="納品",
            emoji="📦",
            style=discord.ButtonStyle.primary,
            custom_id="ticket_delivery"
        )

    async def callback(self, interaction):

        if not is_staff(interaction.user):

            await interaction.response.send_message(
                "スタッフのみ使用できます。",
                ephemeral=True
            )

            return

        await interaction.response.send_modal(
            DeliveryModal()
        )


# =========================================================
# チケット終了
# =========================================================

class CloseButton(
    discord.ui.Button
):

    def __init__(self):

        super().__init__(
            label="クローズ",
            emoji="🔒",
            style=discord.ButtonStyle.danger,
            custom_id="ticket_close"
        )

    async def callback(self, interaction):

        ticket = get_ticket(
            interaction.channel.id
        )

        if not ticket:

            await interaction.response.send_message(
                "ここは依頼チケットではありません。",
                ephemeral=True
            )

            return

        owner_id = ticket[2]

        if (
            interaction.user.id != owner_id
            and not is_staff(interaction.user)
        ):

            await interaction.response.send_message(
                "この操作を行う権限がありません。",
                ephemeral=True
            )

            return

        cursor.execute(
            """
            UPDATE tickets
            SET closed = 1,
                status = '完了'
            WHERE channel_id = ?
            """,
            (interaction.channel.id,)
        )

        db.commit()

        # 依頼者

        member = interaction.guild.get_member(
            owner_id
        )

        if member:

            try:

                await interaction.channel.set_permissions(
                    member,
                    send_messages=False
                )

            except:
                pass

        # チャンネル名

        try:

            await interaction.channel.edit(
                name=(
                    f"closed-{interaction.channel.name}"
                )[:100]
            )

        except:
            pass

        await interaction.response.send_message(
            "🔒 **依頼を完了しました。**"
        )

        await interaction.channel.send(
            "⭐ **ご依頼ありがとうございました！**\n"
            "よろしければ下のボタンからレビューをお願いします。",
            view=ReviewView(
                owner_id,
                interaction.channel.id
            )
        )


# =========================================================
# チケット操作View
# =========================================================

class TicketControlView(
    discord.ui.View
):

    def __init__(self):

        super().__init__(
            timeout=None
        )

        self.add_item(
            AssignButton()
        )

        self.add_item(
            StatusSelect()
        )

        self.add_item(
            QuoteButton()
        )

        self.add_item(
            DeliveryButton()
        )

        self.add_item(
            CloseButton()
        )


# =========================================================
# レビュー
# =========================================================

class ReviewModal(discord.ui.Modal):

    def __init__(
        self,
        owner_id,
        channel_id,
        rating
    ):

        super().__init__(
            title=f"⭐ {rating}つ星レビュー"
        )

        self.owner_id = owner_id
        self.channel_id = channel_id
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

    async def on_submit(self, interaction):

        if interaction.user.id != self.owner_id:

            await interaction.response.send_message(
                "依頼者本人のみレビューできます。",
                ephemeral=True
            )

            return

        cursor.execute(
            """
            SELECT id
            FROM reviews
            WHERE ticket_channel_id = ?
            """,
            (self.channel_id,)
        )

        if cursor.fetchone():

            await interaction.response.send_message(
                "この依頼はすでにレビュー済みです。",
                ephemeral=True
            )

            return

        cursor.execute(
            """
            SELECT guild_id
            FROM tickets
            WHERE channel_id = ?
            """,
            (self.channel_id,)
        )

        row = cursor.fetchone()

        if not row:

            await interaction.response.send_message(
                "依頼情報が見つかりません。",
                ephemeral=True
            )

            return

        guild_id = row[0]

        cursor.execute(
            """
            INSERT INTO reviews
            (
                ticket_channel_id,
                guild_id,
                user_id,
                rating,
                comment
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                self.channel_id,
                guild_id,
                interaction.user.id,
                self.rating,
                self.comment.value
            )
        )

        db.commit()

        # レビュー通知

        if REVIEW_CHANNEL_ID != 0:

            review_channel = (
                interaction.guild.get_channel(
                    REVIEW_CHANNEL_ID
                )
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
                    value=(
                        self.comment.value
                        or "コメントなし"
                    ),
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
            "ありがとうございました。",
            ephemeral=True
        )


class ReviewView(
    discord.ui.View
):

    def __init__(
        self,
        owner_id,
        channel_id
    ):

        super().__init__(
            timeout=None
        )

        self.owner_id = owner_id
        self.channel_id = channel_id

    async def send_review(
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
                self.channel_id,
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

        await self.send_review(
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

        await self.send_review(
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

        await self.send_review(
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

        await self.send_review(
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

        await self.send_review(
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
            "オリジナルDiscord Botの制作\n\n"

            "🏠 **鯖作成・構築依頼**\n"
            "Discordサーバーの作成・構築\n\n"

            "🔧 **Bot導入・設定**\n"
            "Botの導入や各種設定\n\n"

            "🎨 **デザイン依頼**\n"
            "アイコン・バナーなど\n\n"

            "🛠️ **その他**\n"
            "その他の依頼\n\n"

            "下のメニューから依頼内容を選択してください。"
        ),
        color=discord.Color.blurple()
    )

    embed.set_footer(
        text="依頼すると専用チケットが自動作成されます。"
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
    description="自分の依頼履歴を確認します"
)
async def ticket(
    interaction: discord.Interaction
):

    cursor.execute(
        """
        SELECT
            channel_id,
            ticket_type,
            status,
            closed
        FROM tickets
        WHERE guild_id = ?
        AND user_id = ?
        ORDER BY created_at DESC
        LIMIT 10
        """,
        (
            interaction.guild.id,
            interaction.user.id
        )
    )

    rows = cursor.fetchall()

    if not rows:

        await interaction.response.send_message(
            "📭 依頼履歴はありません。",
            ephemeral=True
        )

        return

    text = ""

    for channel_id, ticket_type, status, closed in rows:

        channel = interaction.guild.get_channel(
            channel_id
        )

        channel_text = (
            channel.mention
            if channel
            else "`削除済み`"
        )

        text += (
            f"{get_status_emoji(status)} "
            f"**{ticket_type}** "
            f"{channel_text}\n"
        )

    embed = discord.Embed(
        title="🎫 依頼履歴",
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
    description="レビュー統計を表示します"
)
async def reviews(
    interaction: discord.Interaction
):

    cursor.execute(
        """
        SELECT
            COUNT(*),
            AVG(rating)
        FROM reviews
        WHERE guild_id = ?
        """,
        (interaction.guild.id,)
    )

    count, average = cursor.fetchone()

    if count == 0:

        await interaction.response.send_message(
            "⭐ まだレビューはありません。",
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
# /stats
# =========================================================

@bot.tree.command(
    name="stats",
    description="依頼統計を表示します"
)
async def stats(
    interaction: discord.Interaction
):

    guild_id = interaction.guild.id

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM tickets
        WHERE guild_id = ?
        """,
        (guild_id,)
    )

    total = cursor.fetchone()[0]

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM tickets
        WHERE guild_id = ?
        AND closed = 0
        """,
        (guild_id,)
    )

    active = cursor.fetchone()[0]

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM tickets
        WHERE guild_id = ?
        AND closed = 1
        """,
        (guild_id,)
    )

    completed = cursor.fetchone()[0]

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM reviews
        WHERE guild_id = ?
        """,
        (guild_id,)
    )

    review_count = cursor.fetchone()[0]

    cursor.execute(
        """
        SELECT AVG(rating)
        FROM reviews
        WHERE guild_id = ?
        """,
        (guild_id,)
    )

    average = cursor.fetchone()[0]

    if average is None:
        average_text = "なし"
    else:
        average_text = f"{average:.2f} / 5"

    embed = discord.Embed(
        title="📊 依頼統計",
        color=discord.Color.blurple()
    )

    embed.add_field(
        name="📋 総依頼数",
        value=str(total),
        inline=True
    )

    embed.add_field(
        name="🟢 対応中",
        value=str(active),
        inline=True
    )

    embed.add_field(
        name="✅ 完了",
        value=str(completed),
        inline=True
    )

    embed.add_field(
        name="⭐ レビュー",
        value=str(review_count),
        inline=True
    )

    embed.add_field(
        name="⭐ 平均評価",
        value=average_text,
        inline=True
    )

    await interaction.response.send_message(
        embed=embed
    )


# =========================================================
# /myrequest
# =========================================================

@bot.tree.command(
    name="myrequest",
    description="自分の現在の依頼を確認します"
)
async def myrequest(
    interaction: discord.Interaction
):

    cursor.execute(
        """
        SELECT
            channel_id,
            ticket_type,
            request_name,
            status,
            staff_id,
            quote
        FROM tickets
        WHERE guild_id = ?
        AND user_id = ?
        AND closed = 0
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (
            interaction.guild.id,
            interaction.user.id
        )
    )

    row = cursor.fetchone()

    if not row:

        await interaction.response.send_message(
            "📭 現在対応中の依頼はありません。",
            ephemeral=True
        )

        return

    (
        channel_id,
        ticket_type,
        request_name,
        status,
        staff_id,
        quote
    ) = row

    channel = interaction.guild.get_channel(
        channel_id
    )

    staff_text = "未担当"

    if staff_id:

        staff = interaction.guild.get_member(
            staff_id
        )

        staff_text = (
            staff.mention
            if staff
            else f"<@{staff_id}>"
        )

    embed = discord.Embed(
        title="📋 現在の依頼",
        color=discord.Color.blurple()
    )

    embed.add_field(
        name="種類",
        value=ticket_type,
        inline=False
    )

    embed.add_field(
        name="依頼名",
        value=request_name,
        inline=False
    )

    embed.add_field(
        name="状態",
        value=(
            f"{get_status_emoji(status)} "
            f"{status}"
        ),
        inline=True
    )

    embed.add_field(
        name="担当者",
        value=staff_text,
        inline=True
    )

    embed.add_field(
        name="見積",
        value=quote or "未設定",
        inline=True
    )

    if channel:

        embed.add_field(
            name="チケット",
            value=channel.mention,
            inline=False
        )

    await interaction.response.send_message(
        embed=embed,
        ephemeral=True
    )


# =========================================================
# /forceclose
# =========================================================

@bot.tree.command(
    name="forceclose",
    description="スタッフ権限でチケットを完了します"
)
async def forceclose(
    interaction: discord.Interaction
):

    if not is_staff(interaction.user):

        await interaction.response.send_message(
            "スタッフのみ使用できます。",
            ephemeral=True
        )

        return

    ticket = get_ticket(
        interaction.channel.id
    )

    if not ticket:

        await interaction.response.send_message(
            "ここはチケットではありません。",
            ephemeral=True
        )

        return

    cursor.execute(
        """
        UPDATE tickets
        SET closed = 1,
            status = '完了'
        WHERE channel_id = ?
        """,
        (interaction.channel.id,)
    )

    db.commit()

    await interaction.response.send_message(
        "✅ スタッフ権限で依頼を完了しました。"
    )

    owner_id = ticket[2]

    await interaction.channel.send(
        "⭐ ご依頼ありがとうございました！\n"
        "依頼者は下のボタンからレビューできます。",
        view=ReviewView(
            owner_id,
            interaction.channel.id
        )
    )


# =========================================================
# /help
# =========================================================

@bot.tree.command(
    name="help",
    description="Botの使い方を表示します"
)
async def help_command(
    interaction: discord.Interaction
):

    embed = discord.Embed(
        title="📖 Bot Help",
        description="このBotの主な機能です。",
        color=discord.Color.blurple()
    )

    embed.add_field(
        name="📋 依頼",
        value=(
            "`/setup`\n"
            "依頼受付パネルを設置"
        ),
        inline=False
    )

    embed.add_field(
        name="🎫 ユーザー",
        value=(
            "`/ticket` - 依頼履歴\n"
            "`/myrequest` - 現在の依頼"
        ),
        inline=False
    )

    embed.add_field(
        name="📊 情報",
        value=(
            "`/stats` - 依頼統計\n"
            "`/reviews` - レビュー統計"
        ),
        inline=False
    )

    embed.add_field(
        name="👨‍💻 スタッフ",
        value=(
            "チケット内のボタンから\n"
            "担当・ステータス・見積・納品を管理できます。"
        ),
        inline=False
    )

    await interaction.response.send_message(
        embed=embed,
        ephemeral=True
    )


# =========================================================
# 起動
# =========================================================

if not TOKEN:

    print(
        "❌ DISCORD_TOKEN が設定されていません。"
    )

else:

    bot.run(TOKEN)