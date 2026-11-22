import { Sidebar } from "@/components/Sidebar";

export default async function ReleaseLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ name: string }>;
}) {
  const { name } = await params;
  return (
    <div className="flex gap-6">
      <aside className="hidden w-44 shrink-0 md:block">
        <Sidebar release={name} />
      </aside>
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  );
}
