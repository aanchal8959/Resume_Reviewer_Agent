"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

import { useAuth } from "./AuthContext";

const LINKS = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/jobs", label: "Jobs" },
  { href: "/applications", label: "Applications" },
  { href: "/", label: "Career Profile" },
];

export default function Nav() {
  const pathname = usePathname();
  const router = useRouter();
  const { user, logout } = useAuth();
  return (
    <nav className="flex h-14 shrink-0 items-center border-b border-slate-200 bg-white">
      <div className="mx-auto flex h-full w-full max-w-7xl items-center justify-between px-4">
        <Link href="/" className="text-sm font-extrabold tracking-tight text-indigo-700">
          Job Switch Agent
        </Link>
        <div className="flex items-center gap-1">
          {LINKS.map(({ href, label }) => {
            const active =
              href === "/" ? pathname === "/" : pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition ${
                  active
                    ? "bg-indigo-50 text-indigo-700"
                    : "text-slate-600 hover:bg-slate-100"
                }`}
              >
                {label}
              </Link>
            );
          })}
          <span className="mx-2 h-4 w-px bg-slate-200" />
          {user ? (
            <>
              <span className="hidden text-xs font-medium text-slate-500 sm:inline">{user.email}</span>
              <button
                onClick={() => {
                  logout();
                  router.push("/login");
                }}
                className="rounded-lg px-3 py-1.5 text-xs font-semibold text-slate-600 hover:bg-slate-100"
              >
                Logout
              </button>
            </>
          ) : (
            <>
              <Link
                href="/login"
                className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition ${
                  pathname === "/login" ? "bg-indigo-50 text-indigo-700" : "text-slate-600 hover:bg-slate-100"
                }`}
              >
                Login
              </Link>
              <Link
                href="/signup"
                className="rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-indigo-700"
              >
                Sign up
              </Link>
            </>
          )}
        </div>
      </div>
    </nav>
  );
}
