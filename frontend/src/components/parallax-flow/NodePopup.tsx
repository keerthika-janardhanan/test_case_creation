import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, Upload, Loader2 } from 'lucide-react';
import { PopupData } from './types';

interface NodePopupProps {
  popup: PopupData | null;
  onClose: () => void;
}

export const NodePopup: React.FC<NodePopupProps> = ({ popup, onClose }) => {
  const [values, setValues] = useState<Record<string, any>>({});
  const [files, setFiles] = useState<Record<string, File>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);

  if (!popup) return null;

  const handleInputChange = (name: string, value: any) => {
    setValues((prev) => ({ ...prev, [name]: value }));
  };

  const handleFileChange = (name: string, file: File | null) => {
    if (file) {
      setFiles((prev) => ({ ...prev, [name]: file }));
      setValues((prev) => ({ ...prev, [name]: file }));
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    try {
      await popup.onSubmit(values);
      onClose();
    } catch (error) {
      console.error('Popup submit error:', error);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      >
        <motion.div
          initial={{ scale: 0.9, opacity: 0, y: 20 }}
          animate={{ scale: 1, opacity: 1, y: 0 }}
          exit={{ scale: 0.9, opacity: 0, y: 20 }}
          transition={{ type: 'spring', stiffness: 300, damping: 25 }}
          onClick={(e) => e.stopPropagation()}
          className="relative w-full max-w-2xl mx-4 bg-gradient-to-br from-slate-900/95 to-slate-800/95 backdrop-blur-xl border-2 border-blue-500/30 rounded-3xl shadow-2xl p-8"
        >
          {/* Close Button */}
          <button
            onClick={onClose}
            className="absolute top-4 right-4 p-2 hover:bg-white/10 rounded-lg transition-colors"
          >
            <X className="w-6 h-6 text-gray-400 hover:text-white" />
          </button>

          {/* Title */}
          <h2 className="text-3xl font-bold text-white mb-6">{popup.title}</h2>

          {/* Form */}
          <form onSubmit={handleSubmit} className="space-y-6">
            {popup.fields.map((field) => (
              <div key={field.name}>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  {field.label}
                  {field.required && <span className="text-red-400 ml-1">*</span>}
                </label>

                {field.type === 'text' || field.type === 'number' ? (
                  <input
                    type={field.type}
                    required={field.required}
                    placeholder={field.placeholder}
                    value={values[field.name] || ''}
                    onChange={(e) => handleInputChange(field.name, e.target.value)}
                    className="w-full px-4 py-3 bg-white/5 border border-white/10 rounded-xl text-white placeholder-gray-500 focus:outline-none focus:border-blue-400 transition-colors"
                  />
                ) : field.type === 'textarea' ? (
                  <textarea
                    required={field.required}
                    placeholder={field.placeholder}
                    value={values[field.name] || ''}
                    onChange={(e) => handleInputChange(field.name, e.target.value)}
                    rows={4}
                    className="w-full px-4 py-3 bg-white/5 border border-white/10 rounded-xl text-white placeholder-gray-500 focus:outline-none focus:border-blue-400 transition-colors resize-none"
                  />
                ) : field.type === 'select' ? (
                  <select
                    required={field.required}
                    value={values[field.name] || ''}
                    onChange={(e) => handleInputChange(field.name, e.target.value)}
                    className="w-full px-4 py-3 bg-white/5 border border-white/10 rounded-xl text-white focus:outline-none focus:border-blue-400 transition-colors"
                  >
                    <option value="">Select an option</option>
                    {field.options?.map((opt) => (
                      <option key={opt.value} value={opt.value}>
                        {opt.label}
                      </option>
                    ))}
                  </select>
                ) : field.type === 'file' ? (
                  <div className="relative">
                    <input
                      type="file"
                      id={field.name}
                      required={field.required}
                      onChange={(e) => handleFileChange(field.name, e.target.files?.[0] || null)}
                      className="hidden"
                    />
                    <label
                      htmlFor={field.name}
                      className="flex items-center justify-center w-full px-4 py-3 bg-white/5 border-2 border-dashed border-white/20 rounded-xl text-gray-400 hover:border-blue-400 hover:text-blue-400 cursor-pointer transition-colors"
                    >
                      <Upload className="w-5 h-5 mr-2" />
                      {files[field.name] ? files[field.name].name : field.placeholder || 'Choose file'}
                    </label>
                  </div>
                ) : null}
              </div>
            ))}

            {/* Submit Button */}
            <div className="flex gap-4 pt-4">
              <button
                type="button"
                onClick={onClose}
                disabled={isSubmitting}
                className="flex-1 px-6 py-3 bg-white/5 border border-white/10 rounded-xl text-white hover:bg-white/10 transition-colors disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={isSubmitting}
                className="flex-1 px-6 py-3 bg-gradient-to-r from-blue-600 to-purple-600 rounded-xl text-white font-semibold hover:from-blue-500 hover:to-purple-500 transition-all disabled:opacity-50 flex items-center justify-center gap-2"
              >
                {isSubmitting ? (
                  <>
                    <Loader2 className="w-5 h-5 animate-spin" />
                    Processing...
                  </>
                ) : (
                  'Submit'
                )}
              </button>
            </div>
          </form>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
};
