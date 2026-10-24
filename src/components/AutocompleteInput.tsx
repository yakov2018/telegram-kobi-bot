import React, { useState, useRef, useEffect } from 'react';
import { Search, X, Check } from 'lucide-react';

interface AutocompleteInputProps {
  options?: string[];
  suggestions?: string[];
  value: string;
  onChange: (val: string) => void;
  onSelect?: (val: string) => void;
  placeholder?: string;
  className?: string;
  label?: string;
  icon?: React.ReactNode;
  disabled?: boolean;
}

export const AutocompleteInput: React.FC<AutocompleteInputProps> = ({
  options,
  suggestions,
  value,
  onChange,
  onSelect,
  placeholder = 'הקלד לחיפוש...',
  className,
  label,
  icon,
  disabled = false,
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState(value);
  const containerRef = useRef<HTMLDivElement>(null);

  const items = options || suggestions || [];

  useEffect(() => {
    setQuery(value);
  }, [value]);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const filteredOptions = items
    .filter((opt) => opt.toLowerCase().includes((query || '').toLowerCase().trim()))
    .slice(0, 15);

  const handleSelect = (selected: string) => {
    setQuery(selected);
    onChange(selected);
    if (onSelect) onSelect(selected);
    setIsOpen(false);
  };

  return (
    <div className="relative w-full" ref={containerRef}>
      {label && <label className="block text-xs font-bold text-slate-300 mb-1.5">{label}</label>}
      <div className="relative flex items-center">
        {icon && <span className="absolute right-3 text-slate-400 pointer-events-none">{icon}</span>}
        <input
          type="text"
          disabled={disabled}
          value={query}
          onFocus={() => setIsOpen(true)}
          onChange={(e) => {
            setQuery(e.target.value);
            onChange(e.target.value);
            setIsOpen(true);
          }}
          placeholder={placeholder}
          className={
            className ||
            `w-full bg-slate-900 border border-slate-700 text-white rounded-xl py-2.5 text-xs focus:outline-none focus:border-amber-500 focus:ring-1 focus:ring-amber-500 transition ${
              icon ? 'pr-9 pl-8' : 'px-3 pl-8'
            }`
          }
        />
        {query && (
          <button
            type="button"
            onClick={() => {
              setQuery('');
              onChange('');
            }}
            className="absolute left-2.5 text-slate-500 hover:text-slate-300 p-0.5"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        )}
      </div>

      {isOpen && filteredOptions.length > 0 && (
        <div className="absolute z-50 mt-1 w-full bg-slate-900 border border-slate-700 rounded-xl shadow-2xl max-h-48 overflow-y-auto divide-y divide-slate-800">
          {filteredOptions.map((opt) => (
            <button
              key={opt}
              type="button"
              onClick={() => handleSelect(opt)}
              className="w-full text-right px-3.5 py-2 text-xs text-slate-200 hover:bg-slate-800 hover:text-white transition flex items-center justify-between cursor-pointer"
            >
              <span>{opt}</span>
              {opt === query && <Check className="w-3.5 h-3.5 text-amber-400" />}
            </button>
          ))}
        </div>
      )}
    </div>
  );
};
