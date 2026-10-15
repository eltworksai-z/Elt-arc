import type { Metadata } from "next";
import type { ReactNode } from "react";
import { Sidebar } from "@/components/shell/Sidebar";
import "./globals.css";

export const metadata: Metadata = {
  title: "ARIA — Voice troubleshooting agent",
  description: "Voice-first knowledge and troubleshooting agent for industrial machines",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="flex h-screen overflow-hidden">
          <Sidebar />
          <main className="min-w-0 flex-1 overflow-hidden">{children}</main>
        </div>
      </body>
    </html>
  );
}
