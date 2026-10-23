import React, { Component, ErrorInfo, ReactNode } from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
  errorInfo: ErrorInfo | null;
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null,
    errorInfo: null,
  };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error, errorInfo: null };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('🚨 [ErrorBoundary caught rendering error]:', error, errorInfo);
    this.setState({ errorInfo });
  }

  public handleReload = () => {
    this.setState({ hasError: false, error: null, errorInfo: null });
    window.location.reload();
  };

  public render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col items-center justify-center p-6 text-center font-sans" dir="rtl">
          <div className="w-16 h-16 rounded-2xl bg-red-500/10 border border-red-500/30 flex items-center justify-center text-3xl mb-4 text-red-400">
            <AlertTriangle className="w-8 h-8" />
          </div>
          <h2 className="text-xl font-extrabold text-white mb-2">אירעה שגיאה בטעינת הרכיב</h2>
          <p className="text-xs text-slate-400 max-w-md mb-4 leading-relaxed">
            {this.state.error?.message || 'שגיאת ממשק לא צפויה.'}
          </p>
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-3 max-w-lg w-full text-left font-mono text-[11px] text-red-300 overflow-x-auto mb-6 max-h-32">
            {this.state.error?.stack || String(this.state.error)}
          </div>
          <button
            onClick={this.handleReload}
            className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold text-xs transition shadow-lg cursor-pointer"
          >
            <RefreshCw className="w-4 h-4" />
            <span>רענן אפליקציה</span>
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}
