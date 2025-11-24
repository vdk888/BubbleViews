import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Bubble - Sign In",
  description: "Sign in to Bubble Dashboard",
};

export default function LoginLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="inter_9dc2cc38-module__4FNZBW__variable geist_mono_8d43a2aa-module__8Li5zG__variable antialiased">
        {children}
      </body>
    </html>
  );
}
