import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Layout from './components/Layout';
import Dashboard from './pages/Dashboard';
import DocumentDetail from './pages/DocumentDetail';
import Documents from './pages/Documents';
import QueueManager from './pages/QueueManager';
import Upload from './pages/Upload';
import Video from './pages/Video';
import VideoDetail from './pages/VideoDetail';
import UnifiedSearch from './pages/UnifiedSearch';

function App() {
  return (
    <BrowserRouter>
      <Layout>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/upload" element={<Upload />} />
          <Route path="/queue" element={<QueueManager />} />
          <Route path="/documents" element={<Documents />} />
          <Route path="/documents/:docId" element={<DocumentDetail />} />
          <Route path="/videos" element={<Video />} />
          <Route path="/videos/:videoId" element={<VideoDetail />} />
          <Route path="/search" element={<UnifiedSearch />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  );
}

export default App;
