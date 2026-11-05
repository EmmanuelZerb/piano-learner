import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Piano Learner",
  description: "Apprendre des morceaux au piano à partir d'un audio",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="fr" className="h-full antialiased">
      <body className="flex min-h-full flex-col">{children}</body>
    </html>
  );
}
