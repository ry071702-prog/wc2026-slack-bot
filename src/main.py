from __future__ import annotations

import argparse
import os
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Optional, Sequence

from src.flags import flag_reaction
from src.messages import japan_opponent, japan_poll_reactions
from src.providers.base import JST, Match, Provider
from src.providers.football_data import FootballDataProvider
from src.slack import (
    SlackBotClient,
    SlackSender,
    SlackWebhookClient,
    build_digest_payload,
    build_poll_payload,
    build_poll_result_payload,
    build_prematch_payload,
    build_result_payload,
)
from src.state import NotificationState, StateStore

TOURNAMENT_START_UTC = datetime(2026, 6, 11, tzinfo=timezone.utc)
TOURNAMENT_END_UTC = datetime(2026, 7, 21, tzinfo=timezone.utc)
DEFAULT_STATE_PATH = Path("state/notified.json")
MAX_RESULTS_PER_RUN = 10
DEFAULT_QUIET_HOURS = "01:00-06:30"
# 開幕戦 (6/12 4:00 JST) は深夜通知OKのユーザー判断のため、静音は翌朝から有効
QUIET_ACTIVE_FROM_UTC = datetime(2026, 6, 12, 0, 0, tzinfo=timezone.utc)


def parse_quiet_hours(value: Optional[str]) -> Optional[tuple[time, time]]:
    """"HH:MM-HH:MM" を (start, end) に。空文字なら無効 (None)。"""
    if value is None:
        value = DEFAULT_QUIET_HOURS
    value = value.strip()
    if not value:
        return None
    start_raw, end_raw = value.split("-")
    return (time.fromisoformat(start_raw), time.fromisoformat(end_raw))


def is_quiet_time(
    now: datetime, quiet_hours: Optional[tuple[time, time]]
) -> bool:
    """静音時間帯 (JST) かどうか。日跨ぎ指定 (例 23:00-06:00) にも対応。"""
    if quiet_hours is None:
        return False
    start, end = quiet_hours
    now_jst = now.astimezone(JST).time()
    if start <= end:
        return start <= now_jst < end
    return now_jst >= start or now_jst < end


def should_send_prematch(
    match: Match,
    now: datetime,
    notify_minutes_before: int,
    state: NotificationState,
) -> bool:
    if match.status not in {"SCHEDULED", "TIMED"}:
        return False
    if match.id in state["prematch"]:
        return False
    delta = match.utc_kickoff - now.astimezone(timezone.utc)
    return timedelta(0) < delta <= timedelta(minutes=notify_minutes_before)


def should_send_result(match: Match, state: NotificationState) -> bool:
    # 無料APIはFINISHED直後にスコア未反映のことがある → スコアが入るまで次回実行に持ち越す
    return (
        match.status == "FINISHED"
        and match.id not in state["result"]
        and match.score.home is not None
        and match.score.away is not None
    )


def _supports_reactions(slack: SlackSender) -> bool:
    """リアクション投票に必要な API (Bot Token クライアント) を備えているか。
    Incoming Webhook はリアクションを扱えないためポール機能はスキップされる。"""
    return all(
        hasattr(slack, attr)
        for attr in ("post_message", "add_reaction", "get_reactions")
    )


def should_post_poll(
    match: Match,
    now: datetime,
    poll_lead_hours: int,
    state: NotificationState,
) -> bool:
    if not match.is_japan:
        return False
    if match.status not in {"SCHEDULED", "TIMED"}:
        return False
    if str(match.id) in state["poll"]:
        return False
    delta = match.utc_kickoff - now.astimezone(timezone.utc)
    return timedelta(0) < delta <= timedelta(hours=poll_lead_hours)


def should_post_poll_result(match: Match, state: NotificationState) -> bool:
    return (
        match.is_japan
        and match.status == "FINISHED"
        and match.score.home is not None
        and match.score.away is not None
        and str(match.id) in state["poll"]
        and match.id not in state["poll_result"]
    )


def is_notify_period(now: datetime) -> bool:
    now_utc = now.astimezone(timezone.utc)
    return TOURNAMENT_START_UTC <= now_utc < TOURNAMENT_END_UTC


def is_digest_period(now: datetime) -> bool:
    current_jst_date = now.astimezone(JST).date()
    return date(2026, 6, 11) <= current_jst_date <= date(2026, 7, 20)


def utc_query_dates_for_jst_day(day: date) -> tuple[date, date]:
    start_jst = datetime.combine(day, time.min, tzinfo=JST)
    end_jst = start_jst + timedelta(days=1) - timedelta(microseconds=1)
    return (
        start_jst.astimezone(timezone.utc).date(),
        end_jst.astimezone(timezone.utc).date(),
    )


def run_notify(
    provider: Provider,
    slack: SlackSender,
    state_store: StateStore,
    now: Optional[datetime] = None,
    notify_minutes_before: int = 15,
    mention_japan: bool = False,
    quiet_hours: Optional[tuple[time, time]] = None,
    poll_lead_hours: int = 14,
) -> None:
    current_time = now or datetime.now(timezone.utc)
    if not is_notify_period(current_time):
        print("notify: outside tournament period; exiting")
        return

    quiet = is_quiet_time(current_time, quiet_hours)
    if quiet:
        print("notify: quiet hours (日本戦のみ通知)")

    state = state_store.load()
    today_jst = current_time.astimezone(JST).date()
    matches = provider.fetch_matches(
        today_jst - timedelta(days=1),
        today_jst + timedelta(days=1),
    )

    prematch_matches = sorted(
        (
            match
            for match in matches
            if should_send_prematch(
                match, current_time, notify_minutes_before, state
            )
            and (not quiet or match.is_japan)
        ),
        key=lambda match: match.utc_kickoff,
    )
    result_matches = sorted(
        (
            match
            for match in matches
            if should_send_result(match, state)
            and (not quiet or match.is_japan)
        ),
        key=lambda match: match.utc_kickoff,
    )[:MAX_RESULTS_PER_RUN]
    live_now = sum(1 for m in matches if m.status in ("IN_PLAY", "PAUSED"))
    print(
        "notify: "
        f"prematch={len(prematch_matches)}, result={len(result_matches)}, "
        f"live_now={live_now}"
    )

    for match in prematch_matches:
        sent = slack.send(build_prematch_payload(match, mention_japan))
        if sent and not slack.dry_run:
            state["prematch"].append(match.id)
            state_store.save(state)

    for match in result_matches:
        sent = slack.send(build_result_payload(match))
        if sent and not slack.dry_run:
            state["result"].append(match.id)
            state_store.save(state)

    # 日本戦の勝敗予想リアクション投票 (静音時間とは無関係、Bot Token クライアントのみ)
    if _supports_reactions(slack):
        run_poll(provider, slack, state_store, state, current_time, matches, poll_lead_hours)


def run_poll(
    provider: Provider,
    slack: SlackSender,
    state_store: StateStore,
    state: NotificationState,
    now: datetime,
    matches: list[Match],
    poll_lead_hours: int,
) -> None:
    """日本戦の勝敗予想ポール: 試合前に投票募集、試合後に集計を発表する。"""
    poll_matches = sorted(
        (m for m in matches if should_post_poll(m, now, poll_lead_hours, state)),
        key=lambda m: m.utc_kickoff,
    )
    for match in poll_matches:
        response = slack.post_message(build_poll_payload(match))
        if not response or not response.get("ok"):
            continue
        ts = response.get("ts")
        for name in japan_poll_reactions(match):
            slack.add_reaction(ts, name)
        if not slack.dry_run:
            state["poll"][str(match.id)] = ts
            state_store.save(state)

    result_matches = sorted(
        (m for m in matches if should_post_poll_result(m, state)),
        key=lambda m: m.utc_kickoff,
    )
    for match in result_matches:
        data = slack.get_reactions(state["poll"][str(match.id)])
        if data is None:
            # 取得失敗 (レート制限・一時障害等) → 次回実行で再試行
            continue
        reactions = (data.get("message") or {}).get("reactions") or []
        counts = {item.get("name"): item.get("count", 0) for item in reactions}
        opponent_flag = flag_reaction(japan_opponent(match))
        votes_jp = max(0, counts.get("jp", 0) - 1)
        votes_draw = max(0, counts.get("handshake", 0) - 1)
        votes_opp = max(0, counts.get(opponent_flag, 0) - 1)
        sent = slack.send(
            build_poll_result_payload(match, votes_jp, votes_draw, votes_opp)
        )
        if sent and not slack.dry_run:
            state["poll_result"].append(match.id)
            state_store.save(state)


def run_digest(
    provider: Provider,
    slack: SlackSender,
    state_store: StateStore,
    now: Optional[datetime] = None,
) -> None:
    current_time = now or datetime.now(timezone.utc)
    if not is_digest_period(current_time):
        print("digest: outside tournament period; exiting")
        return

    state = state_store.load()
    today_jst = current_time.astimezone(JST).date()
    date_key = today_jst.isoformat()
    if date_key in state["digest_dates"] and not slack.dry_run:
        print(f"digest: already sent for {date_key}; exiting")
        return

    tomorrow_jst = today_jst + timedelta(days=1)
    date_from, _ = utc_query_dates_for_jst_day(today_jst)
    _, date_to = utc_query_dates_for_jst_day(tomorrow_jst)
    fetched_matches = provider.fetch_matches(date_from, date_to)
    matches = [
        match
        for match in fetched_matches
        if match.kickoff_jst.date() == today_jst
    ]
    tomorrow_matches = [
        match
        for match in fetched_matches
        if match.kickoff_jst.date() == tomorrow_jst
    ]
    if not matches and not tomorrow_matches:
        print(f"digest: no matches on {date_key} nor next day; skipping")
        return
    sent = slack.send(
        build_digest_payload(
            matches,
            today_jst,
            tomorrow_matches=tomorrow_matches,
            tomorrow=tomorrow_jst,
        )
    )
    if sent and not slack.dry_run:
        state["digest_dates"].append(date_key)
        state_store.save(state)


def parse_bool(value: Optional[str], default: bool = False) -> bool:
    if value is None or value == "":
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"invalid boolean value: {value}")


def create_slack_client(dry_run: bool) -> SlackSender:
    """Bot Token があれば chat.postMessage、なければ Incoming Webhook で送る。"""
    token = os.getenv("SLACK_BOT_TOKEN")
    channel = os.getenv("SLACK_CHANNEL_ID")
    if token and channel:
        print("slack: using bot token (chat.postMessage)")
        return SlackBotClient(token=token, channel=channel, dry_run=dry_run)
    print("slack: using incoming webhook")
    return SlackWebhookClient(
        webhook_url=os.getenv("SLACK_WEBHOOK_URL"),
        dry_run=dry_run,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Post 2026 FIFA World Cup notifications to Slack."
    )
    parser.add_argument(
        "--mode",
        choices=("notify", "digest"),
        default=os.getenv("MODE", "notify"),
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    now = datetime.now(timezone.utc)
    if args.mode == "notify" and not is_notify_period(now):
        print("notify: outside tournament period; exiting before API setup")
        return 0
    if args.mode == "digest" and not is_digest_period(now):
        print("digest: outside tournament period; exiting before API setup")
        return 0

    dry_run = parse_bool(os.getenv("DRY_RUN"), default=False)
    mention_japan = parse_bool(os.getenv("MENTION_JAPAN"), default=False)
    notify_minutes = int(os.getenv("NOTIFY_MINUTES_BEFORE", "15"))
    if notify_minutes <= 0:
        raise ValueError("NOTIFY_MINUTES_BEFORE must be greater than zero")
    poll_lead_hours = int(os.getenv("POLL_LEAD_HOURS", "14"))

    provider = FootballDataProvider(
        api_key=os.getenv("FOOTBALL_DATA_API_KEY", "")
    )
    slack = create_slack_client(dry_run)
    state_store = StateStore(DEFAULT_STATE_PATH)

    if args.mode == "notify":
        run_notify(
            provider=provider,
            slack=slack,
            state_store=state_store,
            now=now,
            notify_minutes_before=notify_minutes,
            mention_japan=mention_japan,
            quiet_hours=(
                parse_quiet_hours(os.getenv("QUIET_HOURS"))
                if now >= QUIET_ACTIVE_FROM_UTC
                else None
            ),
            poll_lead_hours=poll_lead_hours,
        )
    else:
        run_digest(
            provider=provider,
            slack=slack,
            state_store=state_store,
            now=now,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
