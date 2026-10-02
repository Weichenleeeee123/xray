import { createRoot } from 'react-dom/client';
import Home from '../app/page';
import '../app/globals.css';

// Keep report bookmarks created before the research home was integrated.
if (/^#\/(?:case\/|cases(?:$|\/)|me(?:$|\/))/.test(location.hash)) {
  location.replace('/xray/' + location.search + location.hash);
} else {
  createRoot(document.getElementById('research-root')!).render(<Home />);
}
