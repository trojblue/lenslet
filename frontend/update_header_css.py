import re

with open('frontend/src/features/ranking/ranking.css', 'r') as f:
    content = f.read()

replacements = [
    (
        r"""\.ranking-header-shell \{
  min-height: 34px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding-block: 3px;
\}""",
        """\.ranking-header-shell {
  min-height: 52px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding-block: 8px;
}"""
    ),
    (
        r"""\.ranking-header-leading \{
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
\}""",
        """\.ranking-header-leading {
  display: flex;
  align-items: center;
  gap: 16px;
  min-width: 0;
}"""
    ),
    (
        r"""\.ranking-header-title \{
  margin: 0;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0\.02em;
  color: var\(--text\);
  white-space: nowrap;
\}""",
        """\.ranking-header-title {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.03em;
  color: var(--text);
  white-space: nowrap;
}"""
    ),
    (
        r"""\.ranking-progress-pill \{
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 22px;
  min-width: 72px;
  padding: 0 9px;
  border-radius: 999px;
  border: 1px solid rgba\(255, 255, 255, 0\.08\);
  background: rgba\(255, 255, 255, 0\.03\);
  box-shadow: inset 0 1px 1px rgba\(0, 0, 0, 0\.2\);
  color: var\(--text-secondary\);
  font-size: 10\.5px;
  font-weight: 500;
  line-height: 1;
  font-family: ui-monospace, 'SFMono-Regular', Menlo, Consolas, monospace;
\}""",
        """\.ranking-progress-pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 24px;
  min-width: 64px;
  padding: 0 10px;
  border-radius: 6px;
  border: 1px solid rgba(255, 255, 255, 0.05);
  background: rgba(0, 0, 0, 0.2);
  color: var(--text-secondary);
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0.05em;
  line-height: 1;
  font-family: ui-monospace, 'SFMono-Regular', Menlo, Consolas, monospace;
}"""
    ),
    (
        r"""\.ranking-header-trailing \{
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  min-width: 0;
  flex-wrap: wrap;
\}""",
        """\.ranking-header-trailing {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 16px;
  min-width: 0;
  flex-wrap: wrap;
}"""
    ),
    (
        r"""\.ranking-nav-group \{
  display: inline-flex;
  align-items: center;
  gap: 6px;
\}

\.ranking-header-trailing \.ranking-nav-group \{
  margin-left: 4px;
\}""",
        """\.ranking-nav-group {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

\.ranking-header-trailing .ranking-nav-group {
  margin-left: 8px;
  padding-left: 20px;
  border-left: 1px solid rgba(255, 255, 255, 0.1);
}"""
    ),
    (
        r"""\.ranking-thumb-size-control \{
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: 1px solid rgba\(255, 255, 255, 0\.08\);
  border-radius: 999px;
  background: rgba\(255, 255, 255, 0\.03\);
  box-shadow: inset 0 1px 2px rgba\(0, 0, 0, 0\.1\);
  padding: 2px 8px;
  min-height: 25px;
  font-size: 10px;
  color: var\(--text-secondary\);
  flex: none;
\}""",
        """\.ranking-thumb-size-control {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  border: none;
  background: transparent;
  box-shadow: none;
  padding: 0;
  min-height: 25px;
  font-size: 11px;
  font-weight: 500;
  color: var(--text-secondary);
  flex: none;
}"""
    ),
    (
        r"""\.ranking-thumb-size-control-header \{
  margin-right: 2px;
\}""",
        """\.ranking-thumb-size-control-header {
  margin-right: 8px;
}"""
    ),
    (
        r"""\.ranking-thumb-size-control > span:first-child \{
  text-transform: uppercase;
  letter-spacing: 0\.07em;
\}""",
        """\.ranking-thumb-size-control > span:first-child {
  letter-spacing: 0.04em;
}"""
    ),
    (
        r"""\.ranking-thumb-size-control input\[type='range'\] \{
  width: 120px;
  height: 14px;
  accent-color: color-mix\(in oklab, var\(--accent\) 72%, white 8%\);
\}""",
        """\.ranking-thumb-size-control input[type='range'] {
  width: 90px;
  height: 4px;
  border-radius: 2px;
  background: rgba(255, 255, 255, 0.1);
  appearance: none;
  outline: none;
  cursor: pointer;
}

\.ranking-thumb-size-control input[type='range']::-webkit-slider-thumb {
  appearance: none;
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: var(--text);
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.4);
  transition: transform 0.1s;
}

\.ranking-thumb-size-control input[type='range']::-webkit-slider-thumb:hover {
  transform: scale(1.2);
}"""
    ),
    (
        r"""\.ranking-button \{
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  min-height: 27px;
  padding: 0 10px;
  border-radius: 999px;
  border: 1px solid rgba\(255, 255, 255, 0\.1\);
  background: rgba\(255, 255, 255, 0\.03\);
  box-shadow: 0 1px 2px rgba\(0, 0, 0, 0\.2\);
  color: var\(--text\);
  font-size: 10\.5px;
  font-weight: 600;
  letter-spacing: 0\.01em;
  text-decoration: none;
  cursor: pointer;
  transition: all 0\.15s ease;
\}""",
        """\.ranking-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  min-height: 30px;
  padding: 0 14px;
  border-radius: 8px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.03);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.1);
  color: var(--text);
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0.02em;
  text-decoration: none;
  cursor: pointer;
  transition: all 0.15s ease;
}"""
    ),
    (
        r"""\.ranking-button-icon \{
  width: 12px;
  height: 12px;
  flex: none;
\}""",
        """\.ranking-button-icon {
  width: 14px;
  height: 14px;
  flex: none;
  opacity: 0.8;
}

\.ranking-button:hover .ranking-button-icon {
  opacity: 1;
}"""
    ),
]

for pat, repl in replacements:
    content, count = re.subn(pat, repl, content)
    if count == 0:
        print(f"Warning: pattern not found:\n{pat[:100]}...\n")

with open('frontend/src/features/ranking/ranking.css', 'w') as f:
    f.write(content)
