import './globals.css';

export const metadata = {
  title: 'Army Archive | Management System',
  description: 'Secure archive management for documents, hierarchy, and approvals.',
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <head>
        <link
          rel="stylesheet"
          href="https://fonts.googleapis.com/icon?family=Material+Icons"
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
