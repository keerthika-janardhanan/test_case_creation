import { useState } from 'react';
import { TestTube, Download, Upload, FileText, Search } from 'lucide-react';

export function TestCasesPageAnimated() {
  const [isLoading] = useState(false);

  return (
    <div className="fade-in">
      <div className="animated-card">
        <div className="flex items-center gap-3 mb-6">
          <div className="p-3 bg-gradient-to-br from-blue-500 to-purple-600 rounded-xl text-white shadow-lg">
            <TestTube className="w-6 h-6" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-white" style={{ fontFamily: 'Fredoka, sans-serif' }}>
              Generate Test Cases
            </h1>
            <p className="text-white/80 text-sm">
              Create comprehensive manual test cases from recordings
            </p>
          </div>
        </div>

        <div className="space-y-6">
          {/* Upload Section */}
          <div className="animated-card bg-white/5">
            <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
              <Upload className="w-5 h-5" />
              Upload Recording
            </h3>
            <div className="border-2 border-dashed border-white/30 rounded-lg p-8 text-center">
              <FileText className="w-12 h-12 text-white/60 mx-auto mb-4" />
              <p className="text-white/80 mb-4">
                Drop your recording metadata files here or click to upload
              </p>
              <input
                type="file"
                accept=".json,.har"
                className="hidden"
                id="file-upload"
              />
              <label
                htmlFor="file-upload"
                className="animated-button cursor-pointer inline-block"
              >
                Choose Files
              </label>
            </div>
          </div>

          {/* Search Vector DB */}
          <div className="animated-card bg-white/5">
            <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
              <Search className="w-5 h-5" />
              Search Vector Database
            </h3>
            <div className="space-y-4">
              <input
                type="text"
                placeholder="Search for existing test flows..."
                className="animated-input"
              />
              <button className="animated-button">
                Search & Generate
              </button>
            </div>
          </div>

          {/* Generate Button */}
          <div className="text-center">
            <button 
              className="animated-button text-lg px-8 py-4"
              disabled={isLoading}
            >
              {isLoading ? (
                <>
                  <div className="loading-spinner mr-3"></div>
                  Generating Test Cases...
                </>
              ) : (
                <>
                  <TestTube className="w-5 h-5 mr-3" />
                  Generate Test Cases
                </>
              )}
            </button>
          </div>

          {/* Download Section */}
          <div className="animated-card bg-white/5">
            <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
              <Download className="w-5 h-5" />
              Download Results
            </h3>
            <p className="text-white/70 mb-4">
              Generated test cases will be available for download in Excel format
            </p>
            <button className="animated-button" disabled>
              <Download className="w-4 h-4 mr-2" />
              Download Excel
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}