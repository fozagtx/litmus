import { BrowserRouter, Route, Routes } from 'react-router-dom';
import { Layout } from './components/Layout';
import { ToastProvider } from './components/Toast';
import AssetDetail from './pages/AssetDetail';
import ExportPage from './pages/ExportPage';
import Landing from './pages/Landing';
import Studio from './pages/Studio';
import Vault from './pages/Vault';
import Verify from './pages/Verify';

export default function App() {
  return (
    <BrowserRouter>
      <ToastProvider>
        <Routes>
          <Route element={<Layout />}>
            <Route path="/" element={<Landing />} />
            <Route path="/studio" element={<Studio />} />
            <Route path="/vault" element={<Vault />} />
            <Route path="/asset/:id" element={<AssetDetail />} />
            <Route path="/verify" element={<Verify />} />
            <Route path="/export" element={<ExportPage />} />
          </Route>
        </Routes>
      </ToastProvider>
    </BrowserRouter>
  );
}
