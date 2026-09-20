import Link from "next/link";
import { WeekActivityChart } from "@/components/WeekActivityChart";
import {
  EmptyState,
  MasteryBar,
  ModeBadge,
  PageHeader,
  StatCard,
  TextLink,
} from "@/components/ui";
import { formatDuration, formatPct, getSelectedChild } from "@/lib/data";
import { createClient } from "@/lib/supabase/server";

export default async function OverviewPage() {
  const child = await getSelectedChild();
  if (!child) {
    return (
      <>
        <PageHeader
          eyebrow="Parent dashboard"
          title="Welcome to lilvro"
          description="Add a child profile to start seeing study sessions, streaks, and mastery."
        />
        <EmptyState
          title="No children yet"
          body="Create a nickname-only profile on the Children page. You can link the voice agent with that child’s ID later."
          action={
            <Link href="/children" className="btn-primary inline-block">
              Add a child
            </Link>
          }
        />
      </>
    );
  }

  const supabase = await createClient();
  const weekAgo = new Date();
  weekAgo.setDate(weekAgo.getDate() - 7);

  const [{ data: stats }, { data: sessions }, { data: mastery }] = await Promise.all([
    supabase.from("child_stats").select("*").eq("child_id", child.id).maybeSingle(),
    supabase
      .from("sessions")
      .select("*")
      .eq("child_id", child.id)
      .gte("started_at", weekAgo.toISOString())
      .order("started_at", { ascending: false }),
    supabase
      .from("mastery_scores")
      .select("*")
      .eq("child_id", child.id)
      .order("score", { ascending: false })
      .limit(5),
  ]);

  const weekSessions = sessions ?? [];
  const weekMinutes = Math.round(
    weekSessions.reduce((sum, s) => sum + (s.duration_seconds ?? 0), 0) / 60,
  );
  const topTopic = mastery?.[0];

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Parent dashboard"
        title={`${child.display_name}'s week`}
        description="Motivation, study time, and what they’re getting more confident with — without interrupting the voice session."
        action={
          <div className="flex items-center gap-2 rounded-full bg-white/80 px-3 py-1.5 text-sm text-[var(--muted)] shadow-sm">
            <span className="live-dot h-2 w-2 rounded-full bg-[var(--accent)]" />
            Synced from study sessions
          </div>
        }
      />

      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard
          label="Current streak"
          value={`${stats?.current_streak_days ?? 0} days`}
          hint={`Best: ${stats?.longest_streak_days ?? 0} days`}
          delay={40}
        />
        <StatCard
          label="Sessions this week"
          value={weekSessions.length}
          hint={`${stats?.sessions_completed ?? 0} all time`}
          delay={90}
        />
        <StatCard
          label="Study time"
          value={`${weekMinutes} min`}
          hint={
            topTopic
              ? `Strongest: ${topTopic.topic} (${formatPct(topTopic.score)})`
              : "Mastery builds as they practice"
          }
          delay={140}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-5">
        <div className="lg:col-span-3">
          <WeekActivityChart sessions={weekSessions} />
        </div>
        <section className="panel page-enter lg:col-span-2" style={{ animationDelay: "120ms" }}>
          <div className="mb-4 flex items-center justify-between gap-3">
            <h2 className="display text-xl">Top topics</h2>
            <TextLink href="/mastery">Mastery</TextLink>
          </div>
          {(mastery ?? []).length === 0 ? (
            <p className="text-sm text-[var(--muted)]">
              Mastery scores appear after walkthrough and teach-back sessions.
            </p>
          ) : (
            <div className="space-y-4">
              {(mastery ?? []).map((m, i) => (
                <MasteryBar key={m.topic} topic={m.topic} score={m.score} delay={i * 60} />
              ))}
            </div>
          )}
        </section>
      </div>

      <section className="panel page-enter" style={{ animationDelay: "160ms" }}>
        <div className="mb-4 flex items-center justify-between gap-3">
          <h2 className="display text-xl">Recent sessions</h2>
          <TextLink href="/activity">All activity</TextLink>
        </div>
        {weekSessions.length === 0 ? (
          <p className="text-sm text-[var(--muted)]">
            No sessions in the last 7 days yet. When they study with lilvro, sessions show up here.
          </p>
        ) : (
          <ul className="divide-y divide-[var(--border)]">
            {weekSessions.slice(0, 5).map((s) => (
              <li key={s.id}>
                <Link
                  href={`/sessions/${s.id}`}
                  className="flex flex-wrap items-center justify-between gap-3 py-3 transition hover:bg-[var(--surface)]/60 sm:px-2"
                >
                  <div className="min-w-0">
                    <p className="font-semibold capitalize text-[var(--ink-soft)]">
                      {s.topic ?? "General practice"}
                    </p>
                    <p className="mt-1 flex flex-wrap items-center gap-2 text-sm text-[var(--muted)]">
                      <ModeBadge mode={s.primary_mode} />
                      <span>{formatDuration(s.duration_seconds)}</span>
                      <span>·</span>
                      <span>{s.turn_count} turns</span>
                    </p>
                  </div>
                  <span className="text-sm text-[var(--muted)]">
                    {new Date(s.started_at).toLocaleDateString(undefined, {
                      weekday: "short",
                      month: "short",
                      day: "numeric",
                    })}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
