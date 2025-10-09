// Register a custom Playwright selector engine for resilient XPath
// Generates union XPath including parent/sibling anchors to self-heal across patches

const { selectors } = require('@playwright/test');

const ENGINE_NAME = 'oracle-xpath';

(async () => {
  await selectors.register(ENGINE_NAME, () => {
    function escapeString(value) {
      if (!value) return '';
      if (value.indexOf("'") === -1) return `'${value}'`;
      if (value.indexOf('"') === -1) return `"${value}"`;
      const parts = value.split("'");
      const tokens = [];
      for (let i = 0; i < parts.length; i += 1) {
        if (parts[i]) tokens.push(`'${parts[i]}'`);
        if (i !== parts.length - 1) tokens.push('"\'"');
      }
      return `concat(${tokens.join(', ')})`;
    }

    function unique(items) {
      const seen = new Set();
      const result = [];
      for (const item of items) {
        if (item && !seen.has(item)) {
          seen.add(item);
          result.push(item);
        }
      }
      return result;
    }

    return {
      create(root, target) {
        const tagName = (target.tagName || 'div').toLowerCase();
        const text = target.innerText ? target.innerText.trim() : '';
        const id = target.getAttribute('id');
        const className = target.getAttribute('class');
        const ariaLabel = target.getAttribute('aria-label');
        const title = target.getAttribute('title');

        const candidates = [];
        if (text) candidates.push(`//*[normalize-space(.)=${escapeString(text)}]`);
        if (ariaLabel && ariaLabel.trim()) {
          const ariaTrim = ariaLabel.trim();
          candidates.push(`//*[@aria-label and normalize-space(@aria-label)=${escapeString(ariaTrim)}]`);
        }
        if (title && title.trim()) {
          const titleTrim = title.trim();
          candidates.push(`//*[@title and normalize-space(@title)=${escapeString(titleTrim)}]`);
        }

        if (id) {
          const prefix = id.split(':')[0];
          if (prefix) candidates.push(`//*[@id and starts-with(@id,'${prefix}')]`);
        }

        if (className) {
          const firstClass = className.split(' ').filter(Boolean)[0];
          if (firstClass) candidates.push(`//${tagName}[contains(@class,'${firstClass}')]`);
        }

        const parent = target.closest ? target.closest('[id], [class], [aria-label], [title]') : null;
        if (parent) {
          const pTag = (parent.tagName || 'div').toLowerCase();
          const pId = parent.getAttribute('id');
          const pCls = parent.getAttribute('class');
          const pAria = parent.getAttribute('aria-label');
          let parentCond = '';
          if (pId) parentCond = `@id and starts-with(@id,'${pId.split(':')[0]}')`;
          else if (pCls) {
            const cls = pCls.split(' ').filter(Boolean)[0];
            if (cls) parentCond = `contains(@class,'${cls}')`;
          } else if (pAria && pAria.trim()) parentCond = `@aria-label`;
          if (parentCond) candidates.push(`//${pTag}[${parentCond}]//${tagName}`);
        }

        const prev = target.previousElementSibling;
        if (prev && prev.innerText) {
          const sText = prev.innerText.trim();
          if (sText) candidates.push(`//*[normalize-space(.)=${escapeString(sText)}]/following::*[self::${tagName}][1]`);
        }

        if (!candidates.length) candidates.push(`//${tagName}`);

        const parts = unique(candidates);
        const joined = parts.length ? parts.join(' | ') : `//${tagName}`;
        return joined;
      },

      query(root, selector) {
        const expr = selector
          .replace(/^oracle-xpath=/, '')
          .replace(/^xpath=/, '');
        return document.evaluate(expr, root, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
      },

      queryAll(root, selector) {
        const expr = selector
          .replace(/^oracle-xpath=/, '')
          .replace(/^xpath=/, '');
        const iterator = document.evaluate(expr, root, null, XPathResult.ORDERED_NODE_ITERATOR_TYPE, null);
        const result = [];
        let node;
        while ((node = iterator.iterateNext())) result.push(node);
        return result;
      }
    };
  });
})();
