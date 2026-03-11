import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncio
import datetime
import json
import logging
import os
import re
import io
from typing import Optional, Dict, List, Any, Callable
try:
    from openai import OpenAI  # type: ignore
except Exception:  # library optional
    OpenAI = None  # type: ignore

# Moderation data persistence
class ModDataManager:
    def __init__(self, data_dir: str = "data"):
        self.data_dir = data_dir
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)

    def _file(self, guild_id: int) -> str:
        return os.path.join(self.data_dir, f"mod_{guild_id}.json")

    def load(self, guild_id: int) -> dict:
        path = self._file(guild_id)
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {
                "modlog_channel_id": None,
                "mute_role_id": None,
                "last_case_id": 0,
                "cases": [],  # [{id, user_id, mod_id, action, reason, created_at, expires_at?}]
                "warns": {},   # { user_id: [ {case_id, reason, created_at, mod_id} ] }
                # Anti-raid & mass mention & filters & tickets
                "antiraid": {
                    "enabled": True,
                    "join_window_seconds": 60,
                    "join_threshold": 5
                },
                "massmention": {
                    "enabled": True,
                    "threshold": 6,
                    "action": "delete"  # delete|mute|warn
                },
                "filters": {
                    "e621_blacklist_enabled": True,
                    "e621_block_tags": ["gore", "scat", "watersports", "loli", "shota"],
                    "e621_require_safe_for_young": True,
                    "scan_attachments": True,
                    "scan_image_links": True,
                    "vision_enabled": False,
                    "vision_provider": "stub",  # stub|custom
                    "vision_min_confidence": 0.85,
                    "vision_blocked_labels": ["gore", "blood", "violence"]
                },
                "tickets": {
                    "category_id": None,
                    "active": {},           # channel_id -> opener_id
                    "active_by_user": {}    # user_id -> channel_id
                }
            }

    def save(self, guild_id: int, data: dict):
        path = self._file(guild_id)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)

# Utilities
DURATION_PATTERN = re.compile(r"(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?", re.I)

def parse_duration(spec: str) -> Optional[datetime.timedelta]:
    if not spec:
        return None
    spec = spec.strip()
    # allow simple digits as minutes
    if spec.isdigit():
        return datetime.timedelta(minutes=int(spec))
    m = DURATION_PATTERN.fullmatch(spec)
    if not m:
        return None
    d, h, mnt, s = m.groups()
    days = int(d) if d else 0
    hours = int(h) if h else 0
    mins = int(mnt) if mnt else 0
    secs = int(s) if s else 0
    if days == hours == mins == secs == 0:
        return None
    return datetime.timedelta(days=days, hours=hours, minutes=mins, seconds=secs)

async def send_ephemeral(ctx: commands.Context, content: Optional[str] = None, *, embed: Optional[discord.Embed] = None):
    # Best-effort ephemeral for slash, fallback to normal send for prefix
    try:
        if hasattr(ctx, "interaction") and ctx.interaction and not ctx.interaction.response.is_done():
            await ctx.interaction.response.send_message(content or None, embed=embed, ephemeral=True)
        else:
            await ctx.send(content or None, embed=embed)
    except Exception:
        try:
            await ctx.send(content or None, embed=embed)
        except Exception:
            pass

class BringusModTools(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.data = ModDataManager()
        self._expire_task_started = False
        self.expirer.start()
        # In-memory recent joins tracking for anti-raid
        self._recent_joins: Dict[int, List[float]] = {}

    async def cog_unload(self):
        if hasattr(self, "expirer") and self.expirer.is_running():
            self.expirer.cancel()

    # ----- Data helpers -----
    def _next_case_id(self, gdata: dict) -> int:
        cid = int(gdata.get("last_case_id", 0)) + 1
        gdata["last_case_id"] = cid
        return cid

    def _add_case(self, guild_id: int, user_id: int, mod_id: int, action: str, reason: str, expires_at: Optional[str] = None) -> int:
        gdata = self.data.load(guild_id)
        case_id = self._next_case_id(gdata)
        case = {
            "id": case_id,
            "user_id": str(user_id),
            "mod_id": str(mod_id),
            "action": action,
            "reason": reason or "No reason provided",
            "created_at": datetime.datetime.utcnow().isoformat(),
        }
        if expires_at:
            case["expires_at"] = expires_at
        gdata.setdefault("cases", []).append(case)
        self.data.save(guild_id, gdata)
        return case_id

    def _get_modlog_channel(self, guild: discord.Guild) -> Optional[discord.TextChannel]:
        gdata = self.data.load(guild.id)
        ch_id = gdata.get("modlog_channel_id")
        if ch_id:
            ch = guild.get_channel(int(ch_id))
            if isinstance(ch, discord.TextChannel):
                return ch
        return None

    async def _ensure_mute_role(self, guild: discord.Guild) -> Optional[discord.Role]:
        gdata = self.data.load(guild.id)
        role_id = gdata.get("mute_role_id")
        role = None
        if role_id:
            role = guild.get_role(int(role_id))
        if role is None:
            try:
                role = await guild.create_role(name="Muted", reason="Moderation mute role")
            except discord.Forbidden:
                return None
            gdata["mute_role_id"] = role.id
            self.data.save(guild.id, gdata)
            # apply basic deny send perms
            for channel in guild.channels:
                try:
                    if isinstance(channel, (discord.TextChannel, discord.Thread)):
                        await channel.set_permissions(role, send_messages=False, add_reactions=False)
                except Exception:
                    continue
        return role

    def _can_act_on(self, ctx: commands.Context, target: discord.Member) -> bool:
        guild: discord.Guild = ctx.guild
        me: discord.Member = guild.me
        if target == guild.owner:
            return False
        if ctx.author == target:
            return False
        if me.top_role <= target.top_role:
            return False
        if ctx.author.top_role <= target.top_role and ctx.author.id != guild.owner_id:
            return False
        return True

    async def _log_case(self, guild: discord.Guild, case_id: int, user: discord.abc.User, mod: discord.abc.User, action: str, reason: str, expires_at: Optional[datetime.datetime] = None):
        ch = self._get_modlog_channel(guild)
        if not ch:
            return
        embed = discord.Embed(title=f"Case #{case_id} · {action}", color=discord.Color.orange(), timestamp=datetime.datetime.utcnow())
        embed.add_field(name="User", value=f"{user} ({user.id})", inline=False)
        embed.add_field(name="Moderator", value=f"{mod} ({mod.id})", inline=False)
        embed.add_field(name="Reason", value=reason or "No reason provided", inline=False)
        if expires_at:
            embed.add_field(name="Expires", value=discord.utils.format_dt(expires_at, style='R'), inline=False)
        try:
            await ch.send(embed=embed)
        except Exception:
            pass

    # ----- Listeners: Anti-raid, Mass mention, e621 blacklist -----
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        guild = member.guild
        gdata = self.data.load(guild.id)
        anti = gdata.get("antiraid", {})
        if not anti.get("enabled", True):
            return
        window = int(anti.get("join_window_seconds", 60))
        threshold = int(anti.get("join_threshold", 5))
        now = datetime.datetime.utcnow().timestamp()
        arr = self._recent_joins.setdefault(guild.id, [])
        arr.append(now)
        # prune
        cutoff = now - window
        self._recent_joins[guild.id] = [t for t in arr if t >= cutoff]
        if len(self._recent_joins[guild.id]) >= threshold:
            # Alert modlog and enable temporary slowmode in the system channel if available
            ch = self._get_modlog_channel(guild)
            try:
                if ch:
                    await ch.send(embed=discord.Embed(title="🚨 Anti-Raid Alert", description=f"{len(self._recent_joins[guild.id])} joins in the last {window}s.", color=discord.Color.red()))
            except Exception:
                pass

    def _count_mentions(self, message: discord.Message) -> int:
        count = len(message.mentions) + len(message.role_mentions)
        if message.mention_everyone:
            count += 5  # weight everyone/here as many mentions
        return count

    def _parse_e621_tags(self, content: str) -> List[str]:
        content = content.lower()
        tags: List[str] = []
        # Look for e621 tags in URL query (?tags=...)
        if "e621.net" in content and "tags=" in content:
            try:
                # naive parse
                q = content.split("tags=", 1)[1]
                # stop at space or &
                end = len(q)
                for sep in [" ", "\n", "&"]:
                    idx = q.find(sep)
                    if idx != -1:
                        end = min(end, idx)
                q = q[:end]
                parts = q.replace("%20", "+").split("+")
                tags.extend([p.strip() for p in parts if p.strip()])
            except Exception:
                pass
        # Also collect space-separated tokens when users paste tags directly
        for token in re.split(r"\s+", content):
            if any(ch.isalpha() for ch in token):
                tags.append(token.strip())
        # Deduplicate
        seen = set()
        out: List[str] = []
        for t in tags:
            if t not in seen:
                out.append(t)
                seen.add(t)
        return out

    def _has_image_media(self, message: discord.Message) -> bool:
        # attachments
        for att in message.attachments:
            ctype = (att.content_type or "").lower()
            name = (att.filename or "").lower()
            if ctype.startswith("image/") or re.search(r"\.(?:png|jpe?g|gif|webp|bmp|tiff?)$", name):
                return True
        # embeds / image links
        for emb in message.embeds:
            try:
                if emb.image and (emb.image.url or '').strip():
                    return True
                if emb.thumbnail and (emb.thumbnail.url or '').strip():
                    return True
                if emb.type in ("image", "gifv", "video"):
                    return True
                if emb.url and re.search(r"\.(?:png|jpe?g|gif|webp|bmp|tiff?)($|\?)", emb.url.lower()):
                    return True
            except Exception:
                continue
        # raw URLs in content
        text = (message.content or "").lower()
        if re.search(r"https?://\S+\.(?:png|jpe?g|gif|webp|bmp|tiff?)($|\?)", text):
            return True
        return False

    def _extract_tokens_from_text_and_files(self, message: discord.Message) -> List[str]:
        tokens: List[str] = []
        text = (message.content or "").lower()
        # split on non-alphanumeric to approximate tags/words
        tokens.extend([t for t in re.split(r"[^a-z0-9]+", text) if t])
        for att in message.attachments:
            name = (att.filename or "").lower()
            base = re.sub(r"\.[a-z0-9]+$", "", name)
            tokens.extend([t for t in re.split(r"[^a-z0-9]+", base) if t])
        # de-duplicate while preserving order
        seen = set()
        out: List[str] = []
        for t in tokens:
            if t not in seen:
                out.append(t)
                seen.add(t)
        return out

    def _iter_image_media(self, message: discord.Message):
        """Yield tuples (url, kind) for each image-like media item for vision scanning."""
        # Attachments
        for att in message.attachments:
            ctype = (att.content_type or "").lower()
            fn = (att.filename or "").lower()
            if ctype.startswith("image/") or re.search(r"\.(?:png|jpe?g|gif|webp)$", fn):
                yield att.url, "attachment"
        # Embeds
        for emb in message.embeds:
            try:
                if emb.image and emb.image.url:
                    yield emb.image.url, "embed_image"
                elif emb.thumbnail and emb.thumbnail.url:
                    yield emb.thumbnail.url, "embed_thumb"
                elif emb.url and re.search(r"\.(?:png|jpe?g|gif|webp)$", emb.url.lower()):
                    yield emb.url, "embed_url"
            except Exception:
                continue
        # Raw URLs in content
        for m in re.finditer(r"https?://\S+\.(?:png|jpe?g|gif|webp)(?:$|\?)", message.content or ""):
            yield m.group(0), "text_url"

    async def _vision_scan(self, message: discord.Message, filt: dict) -> Optional[str]:
        """Vision scan with pluggable provider. Returns reason string if blocked, else None.
        Providers:
          - openai: uses GPT-4o-mini vision to classify blocked labels
          - stub: fallback substring heuristic
        """
        if not filt.get("vision_enabled"):
            return None
        min_conf = float(filt.get("vision_min_confidence", 0.85))
        blocked_labels = [l.lower() for l in filt.get("vision_blocked_labels", [])]
        provider = (filt.get("vision_provider") or "stub").lower()

        # Collect up to a few images to scan to reduce cost
        media = list(self._iter_image_media(message))[:2]
        if not media:
            return None

        async def _stub_scan(url: str, kind: str) -> Optional[str]:
            lower = url.lower()
            for label in blocked_labels:
                if label in lower:
                    conf = 0.9
                    if conf >= min_conf:
                        return f"Vision block: {label} ({conf*100:.0f}% {kind})"
            return None

        if provider == "openai" and OpenAI is not None:
            try:
                client = OpenAI()  # uses OPENAI_API_KEY if present
            except Exception:
                # fallback to stub on init failure
                for url, kind in media:
                    r = await _stub_scan(url, kind)
                    if r:
                        return r
                return None

            # Ask model to choose a single blocked label (if any) with confidence
            sys_prompt = (
                "You are an image safety classifier. Given an image and a list of blocked labels, "
                "decide if the image contains any of those categories. Respond with strict JSON: "
                "{\"blocked\": true|false, \"label\": string|null, \"confidence\": number between 0 and 1}. "
                "Only choose a label from the provided list if blocked=true."
            )
            labels_text = ", ".join(blocked_labels) if blocked_labels else ""
            for url, kind in media:
                try:
                    resp = client.chat.completions.create(
                        model="gpt-4o-mini",
                        temperature=0,
                        messages=[
                            {"role": "system", "content": sys_prompt},
                            {
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": f"Blocked labels: [{labels_text}]\nReturn JSON only."},
                                    {"type": "image_url", "image_url": {"url": url}},
                                ],
                            },
                        ],
                        response_format={"type": "json_object"},
                    )
                    text = resp.choices[0].message.content or "{}"
                    data = json.loads(text)
                    if data.get("blocked"):
                        label = str(data.get("label") or "blocked").lower()
                        conf = float(data.get("confidence") or 0.0)
                        if conf >= min_conf and (not blocked_labels or label in blocked_labels):
                            return f"Vision block: {label} ({conf*100:.0f}% {kind})"
                except Exception:
                    # On any provider error, try stub heuristic for this URL
                    r = await _stub_scan(url, kind)
                    if r:
                        return r
            return None
        else:
            # Stub provider or library missing
            for url, kind in media:
                r = await _stub_scan(url, kind)
                if r:
                    return r
            return None

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        gdata = self.data.load(message.guild.id)
        # Mass mention
        mm = gdata.get("massmention", {})
        if mm.get("enabled", True):
            thresh = int(mm.get("threshold", 6))
            if self._count_mentions(message) >= thresh:
                action = (mm.get("action") or "delete").lower()
                reason = f"Mass mentions (>= {thresh})"
                try:
                    await message.delete()
                except Exception:
                    pass
                # Log and optionally mute/warn
                case_id = self._add_case(message.guild.id, message.author.id, message.guild.me.id if message.guild.me else message.author.id, "MassMention", reason)
                await self._log_case(message.guild, case_id, message.author, message.guild.me or message.author, "MassMention", reason)
                if action == "mute":
                    role = await self._ensure_mute_role(message.guild)
                    if role and isinstance(message.author, discord.Member):
                        try:
                            await message.author.add_roles(role, reason=reason)
                        except Exception:
                            pass
                elif action == "warn":
                    try:
                        await message.channel.send(f"⚠️ <@{message.author.id}> Please avoid mass mentions.")
                    except Exception:
                        pass

        # e621 blacklist filtering (suppress image preview, keep text)
        filt = gdata.get("filters", {})
        if filt.get("e621_blacklist_enabled", True):
            content_lower = (message.content or "").lower()
            # Only act on e621 links so plain words aren't punished
            if "e621.net" in content_lower:
                block = set([t.lower() for t in filt.get("e621_block_tags", [])])
                require_safe_for_young = bool(filt.get("e621_require_safe_for_young", True))
                tags = self._parse_e621_tags(message.content or "")
                tagset = set(tags)
                violated = False
                if block & tagset:
                    violated = True
                if not violated and any(t.startswith("young") for t in tagset):
                    if require_safe_for_young and ("rating:s" not in tagset and "rating:safe" not in tagset):
                        violated = True

                if violated:
                    # Build sanitized e621 URL if possible (remove blocked tags, enforce rating if young)
                    sanitized_content = message.content
                    try:
                        if "e621.net" in content_lower and "tags=" in content_lower:
                            # Extract tag query portion and rebuild without blocked tags
                            block = set([t.lower() for t in filt.get("e621_block_tags", [])])
                            require_safe_for_young = bool(filt.get("e621_require_safe_for_young", True))
                            # Find all URLs with tags=
                            def _sanitize_match(m: re.Match) -> str:
                                url = m.group(0)
                                # Split at tags=
                                pre, post = url.split("tags=", 1)
                                # cut at space or & following
                                end = len(post)
                                for sep in [" ", "\n", "&"]:
                                    idx = post.find(sep)
                                    if idx != -1:
                                        end = min(end, idx)
                                tag_segment = post[:end]
                                remainder = post[end:]
                                raw_tags = tag_segment.replace("%20", "+").split('+')
                                cleaned: List[str] = []
                                has_young = False
                                has_rating_safe = False
                                for t in raw_tags:
                                    tl = t.lower()
                                    if not t:
                                        continue
                                    if tl in block:
                                        continue
                                    if tl.startswith("young"):
                                        has_young = True
                                    if tl in ("rating:s", "rating:safe"):
                                        has_rating_safe = True
                                    cleaned.append(t)
                                if has_young and require_safe_for_young and not has_rating_safe:
                                    cleaned.append("rating:s")
                                new_segment = "+".join(cleaned) if cleaned else "rating:s"
                                return pre + "tags=" + new_segment + remainder

                            sanitized_content = re.sub(r"https?://(?:www\.)?e621\.net/\S*tags=\S+", _sanitize_match, sanitized_content)
                    except Exception:
                        pass
                    # Try to suppress embeds first (removes picture preview, keeps words)
                    suppressed = False
                    try:
                        # discord.py provides both helpers; try either
                        await message.suppress_embeds(True)
                        suppressed = True
                    except Exception:
                        try:
                            await message.edit(suppress=True)
                            suppressed = True
                        except Exception:
                            suppressed = False

                    reason = "e621 blacklist: preview suppressed"

                    # If we couldn't suppress (e.g., missing perms), fall back to repost text without preview
                    if not suppressed:
                        # Sanitize e621 URLs to angle brackets to avoid unfurling
                        def _sanitize_urls(text: str) -> str:
                            try:
                                return re.sub(r"https?://(?:www\.)?e621\.net\S*", lambda m: f"<" + m.group(0) + ">", text or "")
                            except Exception:
                                return text or ""
                        sanitized = _sanitize_urls(sanitized_content or message.content or "")
                        try:
                            await message.delete()
                            # Repost user's words without image preview
                            if sanitized.strip():
                                await message.channel.send(f"{message.author.mention} (image preview removed):\n{sanitized}")
                            suppressed = True
                            reason = "e621 blacklist: message reposted without preview"
                        except Exception:
                            # As a last resort, just send a notice
                            try:
                                await message.channel.send(f"🚫 <@{message.author.id}> That preview isn't allowed here.")
                            except Exception:
                                pass

                    # Log moderation action
                    try:
                        case_id = self._add_case(
                            message.guild.id,
                            message.author.id,
                            message.guild.me.id if message.guild.me else message.author.id,
                            "ContentFilter",
                            reason,
                        )
                        await self._log_case(message.guild, case_id, message.author, message.guild.me or message.author, "ContentFilter", reason)
                    except Exception:
                        pass

        # Generic media scanning (non-e621). Deletes images if blacklisted tokens are present.
        filt = gdata.get("filters", {})
        scan_attachments = bool(filt.get("scan_attachments", True))
        scan_image_links = bool(filt.get("scan_image_links", True))
        if scan_attachments or scan_image_links:
            has_media = self._has_image_media(message)
            if has_media:
                # Vision check first (if enabled)
                if bool(filt.get("vision_enabled")):
                    vision_reason = None
                    try:
                        vision_reason = await self._vision_scan(message, filt)
                    except Exception:
                        vision_reason = None
                    if vision_reason:
                        try:
                            await message.delete()
                        except Exception:
                            pass
                        try:
                            case_id = self._add_case(
                                message.guild.id,
                                message.author.id,
                                message.guild.me.id if message.guild.me else message.author.id,
                                "ContentFilter",
                                vision_reason,
                            )
                            await self._log_case(message.guild, case_id, message.author, message.guild.me or message.author, "ContentFilter", vision_reason)
                        except Exception:
                            pass
                        try:
                            await message.channel.send(f"🚫 <@{message.author.id}> That content isn't allowed here.")
                        except Exception:
                            pass
                        return
                block = set([t.lower() for t in filt.get("e621_block_tags", [])])
                tokens = self._extract_tokens_from_text_and_files(message)
                token_set = set(tokens)
                violated = False
                # direct token match
                if block & token_set:
                    violated = True
                # heuristic substring match (e.g., water_sports vs watersports)
                if not violated:
                    joined_text = " ".join(tokens)
                    for b in block:
                        if re.search(rf"\b{re.escape(b)}\b", joined_text):
                            violated = True
                            break
                # 'young' cannot be proven safe in generic media; if present in text/filename, block
                if not violated and any(t.startswith("young") for t in tokens):
                    violated = True

                if violated:
                    try:
                        await message.delete()
                    except Exception:
                        pass
                    reason = "Blacklisted content detected in media upload/link"
                    try:
                        case_id = self._add_case(
                            message.guild.id,
                            message.author.id,
                            message.guild.me.id if message.guild.me else message.author.id,
                            "ContentFilter",
                            reason,
                        )
                        await self._log_case(message.guild, case_id, message.author, message.guild.me or message.author, "ContentFilter", reason)
                    except Exception:
                        pass
                    try:
                        await message.channel.send(f"🚫 <@{message.author.id}> That content isn't allowed here.")
                    except Exception:
                        pass

    # ----- Settings commands -----
    @commands.hybrid_group(name="modlog", description="Configure moderation log channel")
    @commands.has_guild_permissions(manage_guild=True)
    async def modlog_group(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            gdata = self.data.load(ctx.guild.id)
            ch_id = gdata.get("modlog_channel_id")
            ch_mention = f"<#{ch_id}>" if ch_id else "Not set"
            await send_ephemeral(ctx, f"Modlog channel: {ch_mention}")

    @modlog_group.command(name="set", description="Set the modlog channel")
    async def modlog_set(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        channel = channel or ctx.channel
        gdata = self.data.load(ctx.guild.id)
        gdata["modlog_channel_id"] = channel.id
        self.data.save(ctx.guild.id, gdata)
        await send_ephemeral(ctx, f"✅ Modlog channel set to {channel.mention}")

    @modlog_group.command(name="off", description="Disable modlog")
    async def modlog_off(self, ctx: commands.Context):
        gdata = self.data.load(ctx.guild.id)
        gdata["modlog_channel_id"] = None
        self.data.save(ctx.guild.id, gdata)
        await send_ephemeral(ctx, "✅ Modlog disabled.")

    @modlog_group.command(name="test", description="Send a test entry to modlog")
    async def modlog_test(self, ctx: commands.Context):
        ch = self._get_modlog_channel(ctx.guild)
        if not ch:
            await send_ephemeral(ctx, "No modlog channel configured.")
            return
        await ch.send(embed=discord.Embed(title="Modlog Test", description=f"Requested by {ctx.author.mention}", color=discord.Color.green()))
        await send_ephemeral(ctx, "Sent a test entry to the modlog channel.")

    @commands.hybrid_group(name="muterole", description="Configure or create the mute role")
    @commands.has_guild_permissions(manage_guild=True)
    async def muterole_group(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            gdata = self.data.load(ctx.guild.id)
            rid = gdata.get("mute_role_id")
            role = ctx.guild.get_role(int(rid)) if rid else None
            await send_ephemeral(ctx, f"Mute role: {role.mention if role else 'Not set'}")

    @muterole_group.command(name="set", description="Set the mute role")
    async def muterole_set(self, ctx: commands.Context, role: discord.Role):
        gdata = self.data.load(ctx.guild.id)
        gdata["mute_role_id"] = role.id
        self.data.save(ctx.guild.id, gdata)
        await send_ephemeral(ctx, f"✅ Mute role set to {role.mention}")

    @muterole_group.command(name="create", description="Create a mute role and apply perms")
    async def muterole_create(self, ctx: commands.Context):
        role = await self._ensure_mute_role(ctx.guild)
        if role:
            await send_ephemeral(ctx, f"✅ Created/ensured {role.mention} role and applied basic perms.")
        else:
            await send_ephemeral(ctx, "❌ I couldn't create the mute role (missing permissions).")

    # ----- Anti-raid settings -----
    @commands.hybrid_group(name="antiraid", description="Configure anti-raid thresholds")
    @commands.has_guild_permissions(manage_guild=True)
    async def antiraid_group(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            gdata = self.data.load(ctx.guild.id)
            anti = gdata.get("antiraid", {})
            await send_ephemeral(ctx, f"Anti-raid: {'on' if anti.get('enabled', True) else 'off'} · Window: {anti.get('join_window_seconds', 60)}s · Threshold: {anti.get('join_threshold', 5)}")

    @antiraid_group.command(name="enable", description="Enable anti-raid")
    async def antiraid_enable(self, ctx: commands.Context):
        gdata = self.data.load(ctx.guild.id)
        gdata.setdefault("antiraid", {})["enabled"] = True
        self.data.save(ctx.guild.id, gdata)
        await send_ephemeral(ctx, "✅ Anti-raid enabled.")

    @antiraid_group.command(name="disable", description="Disable anti-raid")
    async def antiraid_disable(self, ctx: commands.Context):
        gdata = self.data.load(ctx.guild.id)
        gdata.setdefault("antiraid", {})["enabled"] = False
        self.data.save(ctx.guild.id, gdata)
        await send_ephemeral(ctx, "✅ Anti-raid disabled.")

    @antiraid_group.command(name="window", description="Set join window in seconds")
    async def antiraid_window(self, ctx: commands.Context, seconds: int):
        gdata = self.data.load(ctx.guild.id)
        gdata.setdefault("antiraid", {})["join_window_seconds"] = max(10, int(seconds))
        self.data.save(ctx.guild.id, gdata)
        await send_ephemeral(ctx, f"✅ Anti-raid window set to {max(10, int(seconds))}s.")

    @antiraid_group.command(name="threshold", description="Set join threshold in window")
    async def antiraid_threshold(self, ctx: commands.Context, count: int):
        gdata = self.data.load(ctx.guild.id)
        gdata.setdefault("antiraid", {})["join_threshold"] = max(2, int(count))
        self.data.save(ctx.guild.id, gdata)
        await send_ephemeral(ctx, f"✅ Anti-raid threshold set to {max(2, int(count))} joins.")

    # ----- Mass mention settings -----
    @commands.hybrid_group(name="massmention", description="Configure mass mention guard")
    @commands.has_guild_permissions(manage_guild=True)
    async def massmention_group(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            gdata = self.data.load(ctx.guild.id)
            mm = gdata.get("massmention", {})
            await send_ephemeral(ctx, f"MassMention: {'on' if mm.get('enabled', True) else 'off'} · Threshold: {mm.get('threshold', 6)} · Action: {mm.get('action', 'delete')}")

    @massmention_group.command(name="enable", description="Enable mass mention guard")
    async def massmention_enable(self, ctx: commands.Context):
        gdata = self.data.load(ctx.guild.id)
        gdata.setdefault("massmention", {})["enabled"] = True
        self.data.save(ctx.guild.id, gdata)
        await send_ephemeral(ctx, "✅ Mass mention guard enabled.")

    @massmention_group.command(name="disable", description="Disable mass mention guard")
    async def massmention_disable(self, ctx: commands.Context):
        gdata = self.data.load(ctx.guild.id)
        gdata.setdefault("massmention", {})["enabled"] = False
        self.data.save(ctx.guild.id, gdata)
        await send_ephemeral(ctx, "✅ Mass mention guard disabled.")

    @massmention_group.command(name="threshold", description="Set mass mention threshold")
    async def massmention_threshold(self, ctx: commands.Context, count: int):
        gdata = self.data.load(ctx.guild.id)
        gdata.setdefault("massmention", {})["threshold"] = max(3, int(count))
        self.data.save(ctx.guild.id, gdata)
        await send_ephemeral(ctx, f"✅ Mass mention threshold set to {max(3, int(count))}.")

    @massmention_group.command(name="action", description="Set action: delete, mute, or warn")
    async def massmention_action(self, ctx: commands.Context, action: str):
        act = action.lower()
        if act not in ("delete", "mute", "warn"):
            await send_ephemeral(ctx, "Action must be delete, mute, or warn.")
            return
        gdata = self.data.load(ctx.guild.id)
        gdata.setdefault("massmention", {})["action"] = act
        self.data.save(ctx.guild.id, gdata)
        await send_ephemeral(ctx, f"✅ Mass mention action set to {act}.")

    # ----- Filters (e621 blacklist) -----
    @commands.hybrid_group(name="filter", description="Configure content filters")
    @commands.has_guild_permissions(manage_guild=True)
    async def filter_group(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            gdata = self.data.load(ctx.guild.id)
            fcfg = gdata.get("filters", {})
            await send_ephemeral(ctx, f"e621 blacklist: {'on' if fcfg.get('e621_blacklist_enabled', True) else 'off'} | require_safe_for_young: {fcfg.get('e621_require_safe_for_young', True)}\nBlocked tags: {', '.join(fcfg.get('e621_block_tags', []))}")

    @filter_group.command(name="e621", description="Enable/disable e621 blacklist")
    async def filter_e621(self, ctx: commands.Context, enabled: bool):
        gdata = self.data.load(ctx.guild.id)
        gdata.setdefault("filters", {})["e621_blacklist_enabled"] = bool(enabled)
        self.data.save(ctx.guild.id, gdata)
        await send_ephemeral(ctx, f"✅ e621 blacklist {'enabled' if enabled else 'disabled'}.")

    @filter_group.command(name="youngsafe", description="Require rating:s for young tag")
    async def filter_youngsafe(self, ctx: commands.Context, required: bool):
        gdata = self.data.load(ctx.guild.id)
        gdata.setdefault("filters", {})["e621_require_safe_for_young"] = bool(required)
        self.data.save(ctx.guild.id, gdata)
        await send_ephemeral(ctx, f"✅ Require rating:s with young set to {required}.")

    @filter_group.command(name="tags", description="Set blocked e621 tags (space separated)")
    async def filter_tags(self, ctx: commands.Context, *, tags: str):
        tag_list = [t.strip().lower() for t in tags.split() if t.strip()]
        gdata = self.data.load(ctx.guild.id)
        gdata.setdefault("filters", {})["e621_block_tags"] = tag_list
        self.data.save(ctx.guild.id, gdata)
        await send_ephemeral(ctx, f"✅ Blocked tags updated: {', '.join(tag_list)}")

    # ----- Moderation core -----
    @commands.hybrid_command(name="kick", description="Kick a member")
    @commands.has_guild_permissions(kick_members=True)
    async def kick(self, ctx: commands.Context, member: discord.Member, *, reason: Optional[str] = None):
        if not self._can_act_on(ctx, member):
            await send_ephemeral(ctx, "❌ I/You cannot act on that user due to role hierarchy.")
            return
        try:
            await member.kick(reason=reason or f"Kicked by {ctx.author}")
            case_id = self._add_case(ctx.guild.id, member.id, ctx.author.id, "Kick", reason or "No reason")
            await self._log_case(ctx.guild, case_id, member, ctx.author, "Kick", reason or "No reason")
            await send_ephemeral(ctx, f"✅ Kicked {member} · Case #{case_id}")
        except discord.Forbidden:
            await send_ephemeral(ctx, "❌ Missing permissions to kick that member.")

    @commands.hybrid_command(name="ban", description="Ban a user")
    @commands.has_guild_permissions(ban_members=True)
    async def ban(self, ctx: commands.Context, member: discord.Member, *, reason: Optional[str] = None):
        if not self._can_act_on(ctx, member):
            await send_ephemeral(ctx, "❌ I/You cannot act on that user due to role hierarchy.")
            return
        try:
            await member.ban(reason=reason or f"Banned by {ctx.author}")
            case_id = self._add_case(ctx.guild.id, member.id, ctx.author.id, "Ban", reason or "No reason")
            await self._log_case(ctx.guild, case_id, member, ctx.author, "Ban", reason or "No reason")
            await send_ephemeral(ctx, f"✅ Banned {member} · Case #{case_id}")
        except discord.Forbidden:
            await send_ephemeral(ctx, "❌ Missing permissions to ban that member.")

    @commands.hybrid_command(name="softban", description="Softban (ban then unban to purge messages)")
    @commands.has_guild_permissions(ban_members=True)
    async def softban(self, ctx: commands.Context, member: discord.Member, *, reason: Optional[str] = None):
        if not self._can_act_on(ctx, member):
            await send_ephemeral(ctx, "❌ I/You cannot act on that user due to role hierarchy.")
            return
        try:
            await member.ban(reason=reason or f"Softban by {ctx.author}")
            await asyncio.sleep(1)
            await ctx.guild.unban(member, reason="Softban unban")
            case_id = self._add_case(ctx.guild.id, member.id, ctx.author.id, "Softban", reason or "No reason")
            await self._log_case(ctx.guild, case_id, member, ctx.author, "Softban", reason or "No reason")
            await send_ephemeral(ctx, f"✅ Softbanned {member} · Case #{case_id}")
        except discord.Forbidden:
            await send_ephemeral(ctx, "❌ Missing permissions to softban that member.")

    @commands.hybrid_command(name="unban", description="Unban a user by ID or name#discrim")
    @commands.has_guild_permissions(ban_members=True)
    async def unban(self, ctx: commands.Context, target: str, *, reason: Optional[str] = None):
        bans = await ctx.guild.bans()
        entry = None
        # try by ID first
        try:
            uid = int(target)
            entry = next((b for b in bans if b.user.id == uid), None)
        except ValueError:
            # try name#discrim
            if "#" in target:
                name, discrim = target.split("#", 1)
                entry = next((b for b in bans if b.user.name == name and b.user.discriminator == discrim), None)
            else:
                entry = next((b for b in bans if b.user.name == target), None)
        if not entry:
            await send_ephemeral(ctx, "❌ Could not find that ban entry.")
            return
        try:
            await ctx.guild.unban(entry.user, reason=reason or f"Unbanned by {ctx.author}")
            case_id = self._add_case(ctx.guild.id, entry.user.id, ctx.author.id, "Unban", reason or "No reason")
            await self._log_case(ctx.guild, case_id, entry.user, ctx.author, "Unban", reason or "No reason")
            await send_ephemeral(ctx, f"✅ Unbanned {entry.user} · Case #{case_id}")
        except discord.Forbidden:
            await send_ephemeral(ctx, "❌ Missing permissions to unban.")

    @commands.hybrid_command(name="tempban", description="Temporarily ban a member: duration then reason")
    @commands.has_guild_permissions(ban_members=True)
    async def tempban(self, ctx: commands.Context, member: discord.Member, duration: str, *, reason: Optional[str] = None):
        if not self._can_act_on(ctx, member):
            await send_ephemeral(ctx, "❌ I/You cannot act on that user due to role hierarchy.")
            return
        delta = parse_duration(duration)
        if not delta:
            await send_ephemeral(ctx, "❌ Invalid duration. Examples: 30m, 2h, 1d2h")
            return
        try:
            await member.ban(reason=reason or f"Tempban by {ctx.author}")
            expires_at = datetime.datetime.utcnow() + delta
            case_id = self._add_case(ctx.guild.id, member.id, ctx.author.id, "Tempban", reason or "No reason", expires_at=expires_at.isoformat())
            await self._log_case(ctx.guild, case_id, member, ctx.author, "Tempban", reason or "No reason", expires_at)
            await send_ephemeral(ctx, f"✅ Tempbanned {member} for {duration} · Case #{case_id}")
        except discord.Forbidden:
            await send_ephemeral(ctx, "❌ Missing permissions to ban that member.")

    @commands.hybrid_command(name="timeout", description="Timeout a member: duration then reason")
    @commands.has_guild_permissions(moderate_members=True)
    async def timeout(self, ctx: commands.Context, member: discord.Member, duration: str, *, reason: Optional[str] = None):
        if not self._can_act_on(ctx, member):
            await send_ephemeral(ctx, "❌ I/You cannot act on that user due to role hierarchy.")
            return
        delta = parse_duration(duration)
        if not delta:
            await send_ephemeral(ctx, "❌ Invalid duration. Examples: 15m, 2h, 1d")
            return
        try:
            until = datetime.datetime.utcnow() + delta
            await member.timeout(until=until, reason=reason or f"Timeout by {ctx.author}")
            case_id = self._add_case(ctx.guild.id, member.id, ctx.author.id, "Timeout", reason or "No reason", expires_at=until.isoformat())
            await self._log_case(ctx.guild, case_id, member, ctx.author, "Timeout", reason or "No reason", until)
            await send_ephemeral(ctx, f"✅ Timed out {member} for {duration} · Case #{case_id}")
        except discord.Forbidden:
            await send_ephemeral(ctx, "❌ Missing permissions to timeout that member.")

    @commands.hybrid_command(name="untimeout", description="Remove timeout from a member")
    @commands.has_guild_permissions(moderate_members=True)
    async def untimeout(self, ctx: commands.Context, member: discord.Member, *, reason: Optional[str] = None):
        try:
            await member.timeout(until=None, reason=reason or f"Untimeout by {ctx.author}")
            case_id = self._add_case(ctx.guild.id, member.id, ctx.author.id, "Untimeout", reason or "No reason")
            await self._log_case(ctx.guild, case_id, member, ctx.author, "Untimeout", reason or "No reason")
            await send_ephemeral(ctx, f"✅ Removed timeout for {member} · Case #{case_id}")
        except discord.Forbidden:
            await send_ephemeral(ctx, "❌ Missing permissions to untimeout that member.")

    @commands.hybrid_command(name="mute", description="Mute a member (role-based). Optional duration.")
    @commands.has_guild_permissions(moderate_members=True)
    async def mute(self, ctx: commands.Context, member: discord.Member, duration: Optional[str] = None, *, reason: Optional[str] = None):
        if not self._can_act_on(ctx, member):
            await send_ephemeral(ctx, "❌ I/You cannot act on that user due to role hierarchy.")
            return
        role = await self._ensure_mute_role(ctx.guild)
        if role is None:
            await send_ephemeral(ctx, "❌ I couldn't create/find a mute role.")
            return
        try:
            await member.add_roles(role, reason=reason or f"Muted by {ctx.author}")
            expires_at = None
            delta = parse_duration(duration) if duration else None
            if delta:
                expires_at = (datetime.datetime.utcnow() + delta).isoformat()
            case_id = self._add_case(ctx.guild.id, member.id, ctx.author.id, "Mute", reason or "No reason", expires_at=expires_at)
            await self._log_case(ctx.guild, case_id, member, ctx.author, "Mute", reason or "No reason", datetime.datetime.fromisoformat(expires_at) if expires_at else None)
            await send_ephemeral(ctx, f"✅ Muted {member}{f' for {duration}' if duration else ''} · Case #{case_id}")
        except discord.Forbidden:
            await send_ephemeral(ctx, "❌ Missing permissions to mute that member.")

    @commands.hybrid_command(name="unmute", description="Unmute a member (role-based)")
    @commands.has_guild_permissions(moderate_members=True)
    async def unmute(self, ctx: commands.Context, member: discord.Member, *, reason: Optional[str] = None):
        role = await self._ensure_mute_role(ctx.guild)
        if role is None:
            await send_ephemeral(ctx, "❌ No mute role configured.")
            return
        try:
            await member.remove_roles(role, reason=reason or f"Unmuted by {ctx.author}")
            case_id = self._add_case(ctx.guild.id, member.id, ctx.author.id, "Unmute", reason or "No reason")
            await self._log_case(ctx.guild, case_id, member, ctx.author, "Unmute", reason or "No reason")
            await send_ephemeral(ctx, f"✅ Unmuted {member} · Case #{case_id}")
        except discord.Forbidden:
            await send_ephemeral(ctx, "❌ Missing permissions to unmute that member.")

    # Warnings and notes
    @commands.hybrid_command(name="warn", description="Warn a member")
    @commands.has_guild_permissions(moderate_members=True)
    async def warn(self, ctx: commands.Context, member: discord.Member, *, reason: Optional[str] = None):
        case_id = self._add_case(ctx.guild.id, member.id, ctx.author.id, "Warn", reason or "No reason")
        gdata = self.data.load(ctx.guild.id)
        warns = gdata.get("warns", {})
        arr = warns.get(str(member.id), [])
        arr.append({
            "case_id": case_id,
            "reason": reason or "No reason provided",
            "mod_id": str(ctx.author.id),
            "created_at": datetime.datetime.utcnow().isoformat()
        })
        warns[str(member.id)] = arr
        gdata["warns"] = warns
        self.data.save(ctx.guild.id, gdata)
        await self._log_case(ctx.guild, case_id, member, ctx.author, "Warn", reason or "No reason")
        await send_ephemeral(ctx, f"✅ Warned {member} · Case #{case_id}")

    @commands.hybrid_command(name="warnings", description="List warnings for a member")
    @commands.has_guild_permissions(moderate_members=True)
    async def warnings(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        member = member or ctx.author
        gdata = self.data.load(ctx.guild.id)
        warns = gdata.get("warns", {}).get(str(member.id), [])
        if not warns:
            await send_ephemeral(ctx, f"No warnings for {member}.")
            return
        embed = discord.Embed(title=f"Warnings for {member}", color=discord.Color.orange())
        for w in warns[-10:]:
            embed.add_field(name=f"Case #{w['case_id']}", value=f"{w['reason']} · <@{w['mod_id']}> · {w['created_at']}", inline=False)
        await send_ephemeral(ctx, embed=embed)

    @commands.hybrid_command(name="clearwarnings", description="Clear warnings for a member (all or N)")
    @commands.has_guild_permissions(moderate_members=True)
    async def clearwarnings(self, ctx: commands.Context, member: discord.Member, count: Optional[int] = None):
        gdata = self.data.load(ctx.guild.id)
        warns = gdata.get("warns", {}).get(str(member.id), [])
        if not warns:
            await send_ephemeral(ctx, f"No warnings for {member}.")
            return
        if count is None or count >= len(warns):
            removed = len(warns)
            warns = []
        else:
            removed = count
            warns = warns[:-count]
        gdata.setdefault("warns", {})[str(member.id)] = warns
        self.data.save(ctx.guild.id, gdata)
        await send_ephemeral(ctx, f"✅ Cleared {removed} warning(s) for {member}.")

    @commands.hybrid_command(name="note", description="Add a staff note to a user")
    @commands.has_guild_permissions(moderate_members=True)
    async def note(self, ctx: commands.Context, member: discord.Member, *, note: str):
        case_id = self._add_case(ctx.guild.id, member.id, ctx.author.id, "Note", note)
        await self._log_case(ctx.guild, case_id, member, ctx.author, "Note", note)
        await send_ephemeral(ctx, f"🗒️ Noted {member} · Case #{case_id}")

    @commands.hybrid_command(name="reason", description="Update the reason for a case")
    @commands.has_guild_permissions(moderate_members=True)
    async def reason(self, ctx: commands.Context, case_id: int, *, reason: str):
        gdata = self.data.load(ctx.guild.id)
        case = next((c for c in gdata.get("cases", []) if int(c.get("id")) == int(case_id)), None)
        if not case:
            await send_ephemeral(ctx, "❌ Case not found.")
            return
        case["reason"] = reason
        self.data.save(ctx.guild.id, gdata)
        await send_ephemeral(ctx, f"✅ Updated reason for Case #{case_id}.")

    @commands.hybrid_command(name="case", description="Show a moderation case")
    @commands.has_guild_permissions(moderate_members=True)
    async def case(self, ctx: commands.Context, case_id: int):
        gdata = self.data.load(ctx.guild.id)
        c = next((c for c in gdata.get("cases", []) if int(c.get("id")) == int(case_id)), None)
        if not c:
            await send_ephemeral(ctx, "❌ Case not found.")
            return
        user_id = int(c["user_id"]) if str(c.get("user_id", "")).isdigit() else None
        mod_id = int(c["mod_id"]) if str(c.get("mod_id", "")).isdigit() else None
        embed = discord.Embed(title=f"Case #{c['id']} · {c['action']}", color=discord.Color.blurple())
        embed.add_field(name="User", value=f"<@{user_id}> ({user_id})" if user_id else c.get("user_id"), inline=False)
        embed.add_field(name="Moderator", value=f"<@{mod_id}> ({mod_id})" if mod_id else c.get("mod_id"), inline=False)
        embed.add_field(name="Reason", value=c.get("reason", "No reason"), inline=False)
        embed.add_field(name="Created", value=c.get("created_at", "?"), inline=True)
        if c.get("expires_at"):
            try:
                dt = datetime.datetime.fromisoformat(c["expires_at"])
                embed.add_field(name="Expires", value=discord.utils.format_dt(dt, style='R'), inline=True)
            except Exception:
                embed.add_field(name="Expires", value=c.get("expires_at"), inline=True)
        await send_ephemeral(ctx, embed=embed)

    @commands.hybrid_command(name="cases", description="Show recent cases for a user")
    @commands.has_guild_permissions(moderate_members=True)
    async def cases(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        gdata = self.data.load(ctx.guild.id)
        items = gdata.get("cases", [])
        if member:
            items = [c for c in items if str(c.get("user_id")) == str(member.id)]
        items = items[-10:]
        if not items:
            await send_ephemeral(ctx, "No cases found.")
            return
        embed = discord.Embed(title="Recent Cases", color=discord.Color.dark_orange())
        for c in items:
            embed.add_field(name=f"#{c['id']} · {c['action']}", value=f"User: <@{c['user_id']}> · Mod: <@{c['mod_id']}>\nReason: {c['reason']}", inline=False)
        await send_ephemeral(ctx, embed=embed)

    # Channel tools
    @commands.hybrid_command(name="purge", description="Bulk delete messages with optional filters")
    @commands.has_guild_permissions(manage_messages=True)
    async def purge(self, ctx: commands.Context, amount: int, user: Optional[discord.Member] = None, contains: Optional[str] = None, bots: Optional[bool] = False):
        if amount <= 0:
            await send_ephemeral(ctx, "Amount must be > 0")
            return
        def check(m: discord.Message):
            if user and m.author.id != user.id:
                return False
            if bots and not m.author.bot:
                return False
            if contains and contains.lower() not in (m.content or "").lower():
                return False
            return True
        try:
            deleted = await ctx.channel.purge(limit=amount, check=check, bulk=True)
            await send_ephemeral(ctx, f"🧹 Deleted {len(deleted)} message(s).")
        except discord.Forbidden:
            await send_ephemeral(ctx, "❌ Missing permissions to manage messages here.")

    @commands.hybrid_command(name="slowmode", description="Set slowmode in this channel (seconds), 0 to disable")
    @commands.has_guild_permissions(manage_channels=True)
    async def slowmode(self, ctx: commands.Context, seconds: int):
        try:
            await ctx.channel.edit(slowmode_delay=max(0, seconds), reason=f"Set by {ctx.author}")
            await send_ephemeral(ctx, f"🐢 Slowmode set to {max(0, seconds)}s.")
        except discord.Forbidden:
            await send_ephemeral(ctx, "❌ Missing permissions to edit channel.")

    @commands.hybrid_command(name="lock", description="Lock this channel (deny @everyone to send)")
    @commands.has_guild_permissions(manage_channels=True)
    async def lock(self, ctx: commands.Context):
        overwrites = ctx.channel.overwrites_for(ctx.guild.default_role)
        overwrites.send_messages = False
        try:
            await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrites, reason=f"Locked by {ctx.author}")
            await send_ephemeral(ctx, "🔒 Channel locked.")
        except discord.Forbidden:
            await send_ephemeral(ctx, "❌ Missing permissions to edit channel.")

    @commands.hybrid_command(name="unlock", description="Unlock this channel")
    @commands.has_guild_permissions(manage_channels=True)
    async def unlock(self, ctx: commands.Context):
        overwrites = ctx.channel.overwrites_for(ctx.guild.default_role)
        overwrites.send_messages = None
        try:
            await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrites, reason=f"Unlocked by {ctx.author}")
            await send_ephemeral(ctx, "🔓 Channel unlocked.")
        except discord.Forbidden:
            await send_ephemeral(ctx, "❌ Missing permissions to edit channel.")

    @commands.hybrid_command(name="nick", description="Change a member's nickname")
    @commands.has_guild_permissions(manage_nicknames=True)
    async def nick(self, ctx: commands.Context, member: discord.Member, *, nickname: str):
        if not self._can_act_on(ctx, member):
            await send_ephemeral(ctx, "❌ I/You cannot act on that user due to role hierarchy.")
            return
        try:
            await member.edit(nick=nickname, reason=f"Nick change by {ctx.author}")
            await send_ephemeral(ctx, f"✅ Nickname changed for {member}.")
        except discord.Forbidden:
            await send_ephemeral(ctx, "❌ Missing permissions to change nickname.")

    @commands.hybrid_command(name="nickreset", description="Reset a member's nickname")
    @commands.has_guild_permissions(manage_nicknames=True)
    async def nickreset(self, ctx: commands.Context, member: discord.Member):
        if not self._can_act_on(ctx, member):
            await send_ephemeral(ctx, "❌ I/You cannot act on that user due to role hierarchy.")
            return
        try:
            await member.edit(nick=None, reason=f"Nick reset by {ctx.author}")
            await send_ephemeral(ctx, f"✅ Nickname reset for {member}.")
        except discord.Forbidden:
            await send_ephemeral(ctx, "❌ Missing permissions to change nickname.")

    # ----- Ticket system -----
    def _tickets(self, guild_id: int) -> dict:
        gdata = self.data.load(guild_id)
        return gdata.setdefault("tickets", {"category_id": None, "active": {}, "active_by_user": {}})

    async def _ensure_ticket_category(self, guild: discord.Guild) -> discord.CategoryChannel:
        gdata = self.data.load(guild.id)
        tcfg = gdata.get("tickets", {})
        cat_id = tcfg.get("category_id")
        cat = guild.get_channel(int(cat_id)) if cat_id else None
        if isinstance(cat, discord.CategoryChannel):
            return cat
        # create or reuse an existing "Tickets" category
        cat = discord.utils.get(guild.categories, name="Tickets")
        if cat is None:
            try:
                cat = await guild.create_category(name="Tickets", reason="Ticket system setup")
            except discord.Forbidden:
                raise
        tcfg["category_id"] = cat.id
        gdata["tickets"] = tcfg
        self.data.save(guild.id, gdata)
        return cat

    async def _open_ticket(self, ctx: commands.Context, subject: Optional[str] = None) -> Optional[discord.TextChannel]:
        guild = ctx.guild
        opener = ctx.author
        gdata = self.data.load(guild.id)
        tickets = self._tickets(guild.id)
        # prevent duplicates
        existing_id = tickets.get("active_by_user", {}).get(str(opener.id))
        if existing_id:
            ch = guild.get_channel(int(existing_id))
            if isinstance(ch, discord.TextChannel):
                await send_ephemeral(ctx, f"You already have an open ticket: {ch.mention}")
                return None
        cat = await self._ensure_ticket_category(guild)
        name = f"ticket-{opener.name.lower()}-{opener.discriminator}"
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            opener: discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True, embed_links=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True, manage_messages=True)
        }
        try:
            ch = await guild.create_text_channel(name=name[:98], category=cat, overwrites=overwrites, reason=f"Ticket opened by {opener}")
        except discord.Forbidden:
            await send_ephemeral(ctx, "❌ I lack permission to create ticket channels.")
            return None
        # record
        tickets.setdefault("active", {})[str(ch.id)] = str(opener.id)
        tickets.setdefault("active_by_user", {})[str(opener.id)] = str(ch.id)
        gdata["tickets"] = tickets
        self.data.save(guild.id, gdata)
        # send welcome
        desc = "Support team will be with you shortly. Please describe your issue." if not subject else f"Subject: {subject}\nOur team will be with you shortly."
        await ch.send(embed=discord.Embed(title="🎫 Ticket Opened", description=desc, color=discord.Color.blue()))
        return ch

    @commands.hybrid_group(name="ticket", description="Ticket system")
    async def ticket_group(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await send_ephemeral(ctx, "Subcommands: open [subject], add <user>, remove <user>, close, transcript")

    @ticket_group.command(name="open", description="Open a ticket")
    async def ticket_open(self, ctx: commands.Context, *, subject: Optional[str] = None):
        ch = await self._open_ticket(ctx, subject)
        if ch is not None:
            await send_ephemeral(ctx, f"✅ Ticket opened: {ch.mention}")

    def _is_ticket_channel(self, guild_id: int, channel_id: int) -> bool:
        gdata = self.data.load(guild_id)
        t = gdata.get("tickets", {})
        return str(channel_id) in (t.get("active", {}) or {})

    @ticket_group.command(name="add", description="Add a user to this ticket")
    @commands.has_guild_permissions(manage_channels=True)
    async def ticket_add(self, ctx: commands.Context, user: discord.Member):
        if not self._is_ticket_channel(ctx.guild.id, ctx.channel.id):
            await send_ephemeral(ctx, "This isn't a ticket channel.")
            return
        try:
            await ctx.channel.set_permissions(user, view_channel=True, send_messages=True, attach_files=True, embed_links=True)
            await send_ephemeral(ctx, f"✅ {user.mention} added to the ticket.")
        except discord.Forbidden:
            await send_ephemeral(ctx, "❌ Missing permissions to edit channel.")

    @ticket_group.command(name="remove", description="Remove a user from this ticket")
    @commands.has_guild_permissions(manage_channels=True)
    async def ticket_remove(self, ctx: commands.Context, user: discord.Member):
        if not self._is_ticket_channel(ctx.guild.id, ctx.channel.id):
            await send_ephemeral(ctx, "This isn't a ticket channel.")
            return
        try:
            await ctx.channel.set_permissions(user, overwrite=None)
            await send_ephemeral(ctx, f"✅ {user.mention} removed from the ticket.")
        except discord.Forbidden:
            await send_ephemeral(ctx, "❌ Missing permissions to edit channel.")

    @ticket_group.command(name="close", description="Close this ticket")
    async def ticket_close(self, ctx: commands.Context):
        if not self._is_ticket_channel(ctx.guild.id, ctx.channel.id):
            await send_ephemeral(ctx, "This isn't a ticket channel.")
            return
        gdata = self.data.load(ctx.guild.id)
        tickets = self._tickets(ctx.guild.id)
        opener_id = tickets.get("active", {}).get(str(ctx.channel.id))
        # lock perms
        try:
            await ctx.channel.set_permissions(ctx.guild.default_role, view_channel=False)
            if opener_id:
                opener = ctx.guild.get_member(int(opener_id))
                if opener:
                    await ctx.channel.set_permissions(opener, view_channel=False)
        except Exception:
            pass
        # remove from active maps
        try:
            tickets.get("active", {}).pop(str(ctx.channel.id), None)
            if opener_id:
                tickets.get("active_by_user", {}).pop(str(opener_id), None)
            gdata["tickets"] = tickets
            self.data.save(ctx.guild.id, gdata)
        except Exception:
            pass
        await ctx.send(embed=discord.Embed(title="✅ Ticket Closed", color=discord.Color.green()))

    @ticket_group.command(name="transcript", description="Export last N messages of this ticket (default 200)")
    async def ticket_transcript(self, ctx: commands.Context, limit: int = 200):
        if not self._is_ticket_channel(ctx.guild.id, ctx.channel.id):
            await send_ephemeral(ctx, "This isn't a ticket channel.")
            return
        limit = max(1, min(1000, limit))
        buf = io.StringIO()
        buf.write(f"Transcript for #{ctx.channel} at {datetime.datetime.utcnow().isoformat()}\n\n")
        try:
            async for m in ctx.channel.history(limit=limit, oldest_first=True):
                line = f"[{m.created_at.isoformat()}] {m.author} ({m.author.id}): {m.content}\n"
                buf.write(line)
        except Exception:
            pass
        buf.seek(0)
        file = discord.File(fp=buf, filename=f"transcript-{ctx.channel.id}.txt")
        await ctx.send(content="Here is the transcript.", file=file)

    # ----- Expiration scheduler -----
    @tasks.loop(seconds=45)
    async def expirer(self):
        # Iterate guilds the bot is in; process expirations
        now = datetime.datetime.utcnow()
        for guild in list(self.bot.guilds):
            gdata = self.data.load(guild.id)
            changed = False
            for case in gdata.get("cases", []):
                expires_at = case.get("expires_at")
                if not expires_at:
                    continue
                try:
                    exp_dt = datetime.datetime.fromisoformat(expires_at)
                except Exception:
                    continue
                if exp_dt > now:
                    continue
                user_id = int(case.get("user_id")) if str(case.get("user_id", "")).isdigit() else None
                if not user_id:
                    continue
                action = case.get("action", "").lower()
                # perform expiry action
                try:
                    if action == "tempban":
                        await guild.unban(discord.Object(id=user_id), reason="Tempban expired")
                        case["expires_at"] = None
                        changed = True
                        await self._log_case(guild, case.get("id", 0), discord.Object(id=user_id), guild.me, "Tempban Expired", "Auto-unban")
                    elif action == "timeout":
                        member = guild.get_member(user_id)
                        if member:
                            await member.timeout(until=None, reason="Timeout expired")
                            case["expires_at"] = None
                            changed = True
                            await self._log_case(guild, case.get("id", 0), member, guild.me, "Timeout Expired", "Auto-untimeout")
                    elif action == "mute":
                        role = await self._ensure_mute_role(guild)
                        member = guild.get_member(user_id)
                        if role and member and role in member.roles:
                            await member.remove_roles(role, reason="Mute expired")
                            case["expires_at"] = None
                            changed = True
                            await self._log_case(guild, case.get("id", 0), member, guild.me, "Mute Expired", "Auto-unmute")
                except Exception:
                    # ignore failure, maybe permissions or already reversed
                    case["expires_at"] = None
                    changed = True
            if changed:
                self.data.save(guild.id, gdata)

    @expirer.before_loop
    async def before_expirer(self):
        await self.bot.wait_until_ready()

async def setup(bot: commands.Bot):
    await bot.add_cog(BringusModTools(bot))
