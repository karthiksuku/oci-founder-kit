import './style.css';

export const metadata = {
  title: 'Launch Notes — founder checklist',
  description: 'A small, stateless checklist for your next app idea.',
};

export default function Layout({ children }) {
  return <html lang="en"><body>
    <a className="skip" href="#main">Skip to content</a>
    <header><a className="brand" href="/">Launch Notes<span> / </span></a><span className="badge">A small start</span></header>
    <main id="main">{children}</main>
    <footer>Preview only. Nothing is saved. Project names appear in the URL; use fictional names.</footer>
  </body></html>;
}
