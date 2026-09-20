import { redirect } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { getChildren, getSelectedChild } from "@/lib/data";
import { createClient } from "@/lib/supabase/server";

export default async function AppLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const kids = await getChildren();
  const selected = await getSelectedChild();

  return (
    <AppShell
      childOptions={kids.map((c) => ({ id: c.id, display_name: c.display_name }))}
      selectedChildId={selected?.id ?? null}
    >
      {children}
    </AppShell>
  );
}
