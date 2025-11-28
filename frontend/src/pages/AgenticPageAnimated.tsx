import { useState } from 'react';
import { Bot, Settings, GitBranch, TestTube, Play, FileText } from 'lucide-react';

export function AgenticPageAnimated() {
  const [repoUrl, setRepoUrl] = useState('');
  const [testDescription, setTestDescription] = useState('');

  return (
    <div className="fade-in">
      <div className="animated-card">
        <div className="flex items-center gap-3 mb-6">
          <div className="p-3 bg-gradient-to-br from-purple-500 to-pink-600 rounded-xl text-white shadow-lg">
            <Bot className="w-6 h-6" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-white" style={{ fontFamily: 'Fredoka, sans-serif' }}>
              AI Script Generator
            </h1>
            <p className="text-white/80 text-sm">
              Generate intelligent Playwright automation scripts
            </p>
          </div>
        </div>

        <div className="space-y-6">
          {/* Repository Settings */}
          <div className="animated-card bg-white/5">
            <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
              <GitBranch className="w-5 h-5" />
              Repository Configuration
            </h3>
            <div className="space-y-4">
              <div>
                <label className="block text-white/80 text-sm font-medium mb-2">
                  Repository URL
                </label>
                <input
                  type="text"
                  value={repoUrl}
                  onChange={(e) => setRepoUrl(e.target.value)}
                  placeholder="https://github.com/username/repo.git"
                  className="animated-input"
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-white/80 text-sm font-medium mb-2">
                    Branch
                  </label>
                  <input
                    type="text"
                    placeholder="main"
                    className="animated-input"
                  />
                </div>
                <div>
                  <label className="block text-white/80 text-sm font-medium mb-2">
                    Framework
                  </label>
                  <select className="animated-input">
                    <option value="playwright">Playwright</option>
                    <option value="cypress">Cypress</option>
                  </select>
                </div>
              </div>
            </div>
          </div>

          {/* Test Description */}
          <div className="animated-card bg-white/5">
            <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
              <FileText className="w-5 h-5" />
              Test Scenario Description
            </h3>
            <textarea
              value={testDescription}
              onChange={(e) => setTestDescription(e.target.value)}
              placeholder="Describe the test scenario you want to automate..."
              rows={6}
              className="animated-input resize-none"
            />
          </div>

          {/* Options */}
          <div className="animated-card bg-white/5">
            <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
              <Settings className="w-5 h-5" />
              Generation Options
            </h3>
            <div className="space-y-3">
              <label className="flex items-center gap-3 text-white/80">
                <input type="checkbox" className="rounded border-white/30" />
                <span>Include Page Object Model</span>
              </label>
              <label className="flex items-center gap-3 text-white/80">
                <input type="checkbox" className="rounded border-white/30" />
                <span>Generate API tests</span>
              </label>
              <label className="flex items-center gap-3 text-white/80">
                <input type="checkbox" className="rounded border-white/30" />
                <span>Add visual regression tests</span>
              </label>
            </div>
          </div>

          {/* Generate Button */}
          <div className="text-center">
            <button className="animated-button text-lg px-8 py-4">
              <Bot className="w-5 h-5 mr-3" />
              Generate AI Script
            </button>
          </div>

          {/* Actions */}
          <div className="grid grid-cols-2 gap-4">
            <button className="animated-button bg-gradient-to-r from-green-500 to-emerald-600">
              <TestTube className="w-4 h-4 mr-2" />
              Run Trial
            </button>
            <button className="animated-button bg-gradient-to-r from-blue-500 to-cyan-600">
              <Play className="w-4 h-4 mr-2" />
              Deploy Script
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}