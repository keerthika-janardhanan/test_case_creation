const os = require("os");
const path = require("path");

function toSlug(value) {
  return (
    String(value || "")
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "") || "scenario"
  );
}

function toCamelCase(value) {
  if (!value) return "";
  const cleaned = String(value)
    .replace(/['"_]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .toLowerCase();
  if (!cleaned) return "";
  return cleaned.replace(/[^a-z0-9]+(.)?/g, (_, ch) =>
    ch ? ch.toUpperCase() : ""
  );
}

function toPascalCase(value) {
  const camel = toCamelCase(value);
  if (!camel) return "";
  return camel.charAt(0).toUpperCase() + camel.slice(1);
}

function normalizeSelector(selector) {
  if (!selector) {
    return "";
  }
  const raw = String(selector).trim();
  const hashIndex = raw.indexOf("#");
  if (hashIndex !== -1) {
    let fragment = raw.slice(hashIndex + 1);
    const cutIndex = fragment.search(/[|\s>+~,.\[]/);
    if (cutIndex !== -1) {
      fragment = fragment.slice(0, cutIndex);
    }
    fragment = fragment.trim();
    if (fragment) {
      return `xpath=//*[@id="${fragment.replace(/"/g, '\\"')}"]`;
    }
  }
  let normalized = raw.replace(/\|[a-zA-Z][\w-]*/g, "");
  normalized = normalized.replace(/\s+/g, " ");
  normalized = normalized.replace(/\s*([>+~,])\s*/g, "$1");
  normalized = normalized.replace(/^\s+/, "").replace(/\s+$/, "");
  return normalized;
}

function extractDataValue(step) {
  const data = typeof step?.data === "string" ? step.data.trim() : "";
  if (!data) {
    return "";
  }
  const colonIndex = data.indexOf(":");
  if (colonIndex !== -1 && colonIndex < data.length - 1) {
    return data.slice(colonIndex + 1).trim();
  }
  return data;
}

function normaliseImport(fromPath, toPath) {
  const rel = path
    .relative(path.dirname(fromPath), toPath)
    .replace(/\\/g, "/");
  if (rel.startsWith(".")) {
    return rel;
  }
  return `./${rel}`;
}

function buildLocatorData(steps) {
  const selectorToKey = new Map();
  const usedKeys = new Set();
  const entries = [];
  const stepRefs = [];

  (steps || []).forEach((step, index) => {
    const locators = step?.locators || {};
    const rawSelector =
      locators.css ||
      locators.playwright ||
      locators.stable ||
      locators.xpath ||
      locators.raw_xpath ||
      locators.selector ||
      "";
    const selector = normalizeSelector(rawSelector);

    if (!selector) {
      stepRefs.push({
        key: null,
        action: step?.action || "",
        dataValue: extractDataValue(step),
        raw: step,
      });
      return;
    }

    let key;
    if (selectorToKey.has(selector)) {
      key = selectorToKey.get(selector);
    } else {
      let base =
        locators.name ||
        locators.title ||
        locators.labels ||
        step.navigation ||
        step.action ||
        `step${index + 1}`;
      base = toCamelCase(base) || `step${index + 1}`;
      key = base;
      let counter = 2;
      while (usedKeys.has(key)) {
        key = `${base}${counter}`;
        counter += 1;
      }
      selectorToKey.set(selector, key);
      usedKeys.add(key);
      entries.push({ key, selector });
    }

    stepRefs.push({
      key,
      action: step?.action || "",
      dataValue: extractDataValue(step),
      raw: step,
    });
  });

  return { entries, stepRefs };
}

function renderPlaywrightTemplate({
  flowName,
  slug,
  steps,
  targetPath,
  suggestedFiles,
}) {
  const defaultLocatorsPath = path.join("locators", `${slug}.ts`);
  const defaultPagePath = path.join(
    "pages",
    `${toPascalCase(slug) || "Generated"}Page.ts`
  );
  const defaultSpecPath = targetPath || path.join("tests", `${slug}.spec.ts`);

  const locatorsPath =
    suggestedFiles?.find((file) => file.type === "locator")?.path ||
    defaultLocatorsPath;
  const pagePath =
    suggestedFiles?.find((file) => file.type === "page")?.path ||
    defaultPagePath;
  const specPath =
    suggestedFiles?.find((file) => file.type === "test")?.path ||
    defaultSpecPath;

  const { entries, stepRefs } = buildLocatorData(steps);
  const locatorsVar =
    toCamelCase(path.basename(locatorsPath, path.extname(locatorsPath))) ||
    `${slug}Locators`;

  const locatorsLines = [
    `const ${locatorsVar} = {`,
    ...entries.map(
      ({ key, selector }) => `  ${key}: ${JSON.stringify(selector)},`
    ),
    "};",
    "",
    `export default ${locatorsVar};`,
  ];
  const locatorsContent =
    locatorsLines.join("\n").replace(/\n{3,}/g, "\n\n").trimEnd() + os.EOL;

  const pageClassName =
    toPascalCase(path.basename(pagePath, path.extname(pagePath))) ||
    "GeneratedPage";
  const locatorPropertyLines = entries.map(
    ({ key }) => `    this.${key} = page.locator(${locatorsVar}.${key});`
  );
  const pageProperties = entries
    .map(({ key }) => `  ${key}: Locator;`)
    .join("\n");
  const pageImportPath = normaliseImport(pagePath, locatorsPath);
  const pageLines = [
    "import { Page, Locator } from '@playwright/test';",
    `import ${locatorsVar} from "${pageImportPath}";`,
    "",
    `class ${pageClassName} {`,
    "  page: Page;",
    pageProperties,
    "",
    "  constructor(page: Page) {",
    "    this.page = page;",
    ...locatorPropertyLines,
    "  }",
    "}",
    "",
    `export default ${pageClassName};`,
  ];
  const pageContent =
    pageLines.join("\n").replace(/\n{3,}/g, "\n\n").trimEnd() + os.EOL;

  const resolvedName = flowName || slug || "Generated Scenario";
  const specImportPath = normaliseImport(specPath, pagePath);
  const specLines = [
    "import { test } from '@playwright/test';",
    `import ${pageClassName} from "${specImportPath}";`,
    "",
    `test.describe('${resolvedName}', () => {`,
    "  test('smoke', async ({ page }) => {",
    `    const flow = new ${pageClassName}(page);`,
  ];

  stepRefs.forEach((ref, index) => {
    const raw = ref.raw || {};
    const note = raw.navigation || raw.action || raw.expected || `Step ${index + 1}`;
    specLines.push(`    // Step ${index + 1}: ${note}`);
    if (!ref.key) {
      specLines.push("    // TODO: No selector provided by refined flow.");
      specLines.push("");
      return;
    }
    const locatorExpr = `flow.${ref.key}`;
    const action = (ref.action || "").toLowerCase();
    const dataValue = ref.dataValue || "";
    if (action.includes("fill") || action.includes("type") || action.includes("enter")) {
      specLines.push(
        `    await ${locatorExpr}.fill(${JSON.stringify(dataValue)});`
      );
    } else if (action.includes("select")) {
      specLines.push(
        `    await ${locatorExpr}.selectOption(${JSON.stringify(dataValue)});`
      );
    } else if (action.includes("press")) {
      specLines.push(
        `    await ${locatorExpr}.press(${JSON.stringify(dataValue || "Enter")});`
      );
    } else if (action.includes("goto") || action.includes("navigate")) {
      specLines.push(
        `    await page.goto(${JSON.stringify(dataValue || "")});`
      );
    } else {
      specLines.push(`    await ${locatorExpr}.click();`);
    }
    if (raw.expected) {
      specLines.push(`    // Expected: ${raw.expected}`);
    }
    specLines.push("");
  });

  specLines.push("  });");
  specLines.push("});");
  const specContent =
    specLines.join("\n").replace(/\n{3,}/g, "\n\n").trimEnd() + os.EOL;

  return [
    { path: locatorsPath, content: locatorsContent },
    { path: pagePath, content: pageContent },
    { path: specPath, content: specContent },
  ];
}

function renderFrameworkTemplate(options) {
  const framework = String(options.framework || "playwright").toLowerCase();
  const flowName = options.flowName || "Generated Scenario";
  const slug = toSlug(options.slug || flowName);
  const steps = Array.isArray(options.steps) ? options.steps : [];
  const targetPath = options.targetPath;
  const suggestedFiles = options.suggestedFiles || [];
  switch (framework) {
    case "playwright":
    default:
      return renderPlaywrightTemplate({
        flowName,
        slug,
        steps,
        targetPath,
        suggestedFiles,
      });
  }
}

module.exports = {
  renderFrameworkTemplate,
};
