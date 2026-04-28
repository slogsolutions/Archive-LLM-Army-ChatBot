import "./globals.css";

export const metadata = {
  title: "Army AI Chat",
  description: "Army document intelligence — powered by RAG + Llama3",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en" className="dark">
      <body className="bg-chat text-[#ececf1] h-screen overflow-hidden">
        {children}
      </body>
    </html>
  );
}
