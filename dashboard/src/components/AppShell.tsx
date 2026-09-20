import Image from "next/image";
import Link from "next/link";
import { ChildSwitcher } from "@/components/ChildSwitcher";
import { NavLinks } from "@/components/NavLinks";
import { createClient } from "@/lib/supabase/server";

export async function AppShell({
  children,
  childOptions,
  selectedChildId,
}: {
  children: React.ReactNode;
  childOptions: { id: string; display_name: string }[];
  selectedChildId: string | null;
}) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-40 border-b border-[var(--border)] bg-[var(--surface)]/90 backdrop-blur-md">
        <div className="mx-auto flex max-w-6xl flex-col gap-3 px-4 py-3 sm:px-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <Link href="/" className="group flex items-center gap-2.5">
              <Image
                src="/lilvro-icon.png"
                alt="Lil-Vro"
                width={32}
                height={32}
                className="h-8 w-8 rounded-lg shadow-sm transition group-hover:opacity-90"
                priority
              />
              <span className="display text-xl tracking-tight">Lil-Vro</span>
              <span className="hidden text-sm text-[var(--muted)] sm:inline">
                for parents
              </span>
            </Link>
            <div className="flex items-center gap-3 sm:gap-4">
              <ChildSwitcher childrenList={childOptions} selectedId={selectedChildId} />
              {user ? (
                <form action="/auth/signout" method="post">
                  <button
                    type="submit"
                    className="rounded-lg px-2 py-1.5 text-sm text-[var(--muted)] transition hover:bg-white/70 hover:text-[var(--ink)]"
                  >
                    Sign out
                  </button>
                </form>
              ) : null}
            </div>
          </div>
          <NavLinks />
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-8 sm:px-6 sm:py-10">{children}</main>
      <footer className="mx-auto max-w-6xl px-4 pb-10 text-sm text-[var(--muted)] sm:px-6">
        Study sessions stay on your family’s account. No kid-facing screen during tutoring with
        Lil-Vro.
      </footer>
    </div>
  );
}
