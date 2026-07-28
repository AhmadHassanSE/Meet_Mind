import { Dialog } from "@headlessui/react";
import {
  BellIcon,
  ChartBarIcon,
  CheckCircleIcon,
  ClipboardDocumentListIcon,
  Cog6ToothIcon,
  CpuChipIcon,
  HomeIcon,
  MagnifyingGlassIcon,
  QueueListIcon,
  UserCircleIcon,
  XMarkIcon,
  BoltIcon,
  ArrowUpTrayIcon,
} from "@heroicons/react/24/outline";
import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import { useAppStore } from "../store";

const nav = [
  { label: "Dashboard", to: "/dashboard", icon: HomeIcon },
  { label: "Meetings", to: "/meetings", icon: ClipboardDocumentListIcon },
  { label: "Action items", to: "/board", icon: CheckCircleIcon },
  { label: "Approval queue", to: "/approvals", icon: QueueListIcon, badge: true },
  { label: "Knowledge graph", to: "/graph", icon: CpuChipIcon },
  { label: "Analytics", to: "/analytics", icon: ChartBarIcon },
];

export function Layout() {
  const [searchOpen, setSearchOpen] = useState(false);
  const { user, approvalCount, setApprovalCount } = useAppStore();
  const location = useLocation();

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setSearchOpen(true);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  useQuery({
    queryKey: ["approval-count"],
    queryFn: async () => {
      const { data } = await api.get("/api/v1/approvals/queue/count");
      setApprovalCount(data.count);
      return data.count as number;
    },
    refetchInterval: 30000,
    retry: false,
  });

  const title = nav.find((item) => location.pathname.startsWith(item.to))?.label ?? "Dashboard";

  return (
    <div className="min-h-screen bg-bg text-primary lg:flex">
      <aside className="fixed inset-x-0 bottom-0 z-40 border-t border-border bg-surface lg:inset-y-0 lg:left-0 lg:w-60 lg:border-r lg:border-t-0">
        <div className="hidden h-20 items-center gap-3 px-5 lg:flex">
          <span className="grid h-10 w-10 place-items-center rounded-md bg-accent text-white"><BoltIcon className="h-6 w-6" /></span>
          <span className="text-xl font-bold">MeetMind</span>
        </div>
        <nav className="grid grid-cols-6 gap-1 p-2 lg:block lg:space-y-1 lg:px-3">
          {nav.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `relative flex min-h-11 items-center justify-center gap-3 rounded-md px-3 text-sm font-medium text-secondary transition hover:bg-surface-2 hover:text-primary lg:justify-start ${
                  isActive ? "bg-surface-2 text-primary lg:before:absolute lg:before:left-0 lg:before:h-7 lg:before:w-1 lg:before:rounded-full lg:before:bg-accent" : ""
                }`
              }
              aria-label={item.label}
            >
              <item.icon className="h-6 w-6 shrink-0" />
              <span className="hidden lg:inline">{item.label}</span>
              {item.badge && approvalCount > 0 ? <span className="absolute right-1 top-1 rounded-full bg-danger px-1.5 text-[10px] font-bold text-white lg:right-3">{approvalCount}</span> : null}
            </NavLink>
          ))}
        </nav>
        <div className="mt-auto hidden border-t border-border p-3 lg:block">
          <NavLink to="/settings" className="flex min-h-11 items-center gap-3 rounded-md px-3 text-sm text-secondary hover:bg-surface-2 hover:text-primary">
            <Cog6ToothIcon className="h-5 w-5" /> Settings
          </NavLink>
          <div className="mt-2 flex items-center gap-3 rounded-md px-3 py-2">
            <UserCircleIcon className="h-9 w-9 text-accent" />
            <div><p className="text-sm font-semibold">{user.name}</p><p className="text-xs text-secondary">{user.email}</p></div>
          </div>
        </div>
      </aside>
      <main className="min-h-screen flex-1 pb-20 lg:ml-60 lg:pb-0">
        <header className="sticky top-0 z-30 border-b border-border bg-bg/90 px-4 py-3 backdrop-blur md:px-8">
          <div className="flex items-center gap-3">
            <h1 className="hidden min-w-40 text-lg font-bold md:block">{title}</h1>
            <button onClick={() => setSearchOpen(true)} className="input flex flex-1 items-center gap-2 text-left text-secondary" aria-label="Search meetings, items, people">
              <MagnifyingGlassIcon className="h-5 w-5" /> Search meetings, items, people...
            </button>
            <NavLink to="/upload" className="btn-primary hidden md:inline-flex"><ArrowUpTrayIcon className="h-5 w-5" /> Upload</NavLink>
            <button className="btn-secondary relative px-3" aria-label="Notifications"><BellIcon className="h-5 w-5" /><span className="absolute right-2 top-2 h-2 w-2 rounded-full bg-danger" /></button>
          </div>
        </header>
        <div className="px-4 py-6 md:px-8"><Outlet /></div>
      </main>
      <Dialog open={searchOpen} onClose={setSearchOpen} className="relative z-50">
        <div className="fixed inset-0 bg-black/60" />
        <div className="fixed inset-x-4 top-16 mx-auto max-w-2xl rounded-lg bg-surface-2 p-4 shadow-modal">
          <div className="flex items-center gap-2 border-b border-border pb-3">
            <MagnifyingGlassIcon className="h-5 w-5 text-secondary" />
            <input autoFocus className="flex-1 bg-transparent text-base" placeholder="Search MeetMind..." />
            <button onClick={() => setSearchOpen(false)} aria-label="Close search"><XMarkIcon className="h-5 w-5" /></button>
          </div>
          {["Meetings", "Action items", "People"].map((group) => <div key={group} className="py-3"><p className="mb-2 text-xs font-bold uppercase text-secondary">{group}</p><div className="rounded-md bg-surface p-3 text-sm text-secondary">Start typing to search {group.toLowerCase()}.</div></div>)}
        </div>
      </Dialog>
    </div>
  );
}
