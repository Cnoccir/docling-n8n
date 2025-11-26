import { ReactNode } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Home, Upload, FileText, Activity, FolderOpen, Youtube, Search } from 'lucide-react';

interface LayoutProps {
  children: ReactNode;
}

const navigation = [
  { name: 'Dashboard', href: '/', icon: Home },
  { name: 'Unified Search', href: '/search', icon: Search },
  { name: 'Upload', href: '/upload', icon: Upload },
  { name: 'Queue', href: '/queue', icon: Activity },
  { name: 'Documents', href: '/documents', icon: FileText },
  { name: 'Videos', href: '/videos', icon: Youtube },
];

export default function Layout({ children }: LayoutProps) {
  const location = useLocation();

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Sidebar */}
      <div className="fixed inset-y-0 left-0 w-64 bg-white border-r border-gray-200">
        <div className="flex flex-col h-full">
          {/* Logo */}
          <div className="p-6 border-b border-gray-200">
            <h1 className="text-2xl font-bold text-blue-600">Docling</h1>
            <p className="text-sm text-gray-500 mt-1">Document Ingestion</p>
          </div>

          {/* Navigation */}
          <nav className="flex-1 p-4 space-y-1">
            {navigation.map((item) => {
              const isActive = location.pathname.startsWith(item.href) && (item.href === '/' ? location.pathname === '/' : true);
              const Icon = item.icon;

              return (
                <Link
                  key={item.name}
                  to={item.href}
                  className={`
                    flex items-center gap-3 px-4 py-3 rounded-lg transition-colors
                    ${
                      isActive
                        ? 'bg-blue-50 text-blue-700 font-medium'
                        : 'text-gray-700 hover:bg-gray-50'
                    }
                  `}
                >
                  <Icon className="w-5 h-5" />
                  <span>{item.name}</span>
                </Link>
              );
            })}
          </nav>

          {/* Footer */}
          <div className="p-4 border-t border-gray-200 space-y-3">
            {/* Google Drive Link */}
            <a
              href="https://drive.google.com/drive/folders/1dmzG9vTj3QX5bn29IgXuUv03FTtJSLKu"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-2 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50 rounded-lg transition-colors group"
            >
              <FolderOpen className="w-4 h-4 text-blue-600 group-hover:text-blue-700" />
              <div className="flex-1">
                <div className="font-medium text-gray-900">Document Library</div>
                <div className="text-xs text-gray-500">View in Google Drive</div>
              </div>
              <svg className="w-3 h-3 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
              </svg>
            </a>

            <p className="text-xs text-gray-500 text-center">
              v1.0.0 • Built with FastAPI & React
            </p>
          </div>
        </div>
      </div>

      {/* Main content */}
      <div className="pl-64">
        <main className="p-8">{children}</main>
      </div>
    </div>
  );
}
