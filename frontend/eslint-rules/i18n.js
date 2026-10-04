// Two guards for the interface catalog (spec 010 §5.7), shared by eslint.config.js and the
// tests that pin them (src/lib/__tests__/lint-rules.test.ts).

/** An accented letter or a guillemet: French that should be in the catalog. It cannot see
 *  unaccented French; review and the English sweep test cover those. */
export const FRENCH = "[àâäçéèêëîïôöûùüÿœÀÂÇÉÈÊËÎÏÔÛÙÜŸŒ«»]";
const MESSAGE =
  "French text belongs in messages/fr.json, read through m.some_key() (spec 010). " +
  "Course text, the model-facing messages in lib/tutor/prompts.ts and the board's notation " +
  "live in the few files this rule is switched off for.";

/** Options for `no-restricted-syntax`: a literal, a template chunk or JSX text with French in it. */
export const noFrenchLiteral = [
  { selector: `Literal[value=/${FRENCH}/]`, message: MESSAGE },
  { selector: `TemplateElement[value.raw=/${FRENCH}/]`, message: MESSAGE },
  { selector: `JSXText[value=/${FRENCH}/]`, message: MESSAGE },
];

/** Files whose French is not interface text. */
export const FRENCH_ALLOWED = [
  "src/lib/tutor/prompts.ts", // what the model is told the student said
  "src/lib/locale.ts", // each language in its own name
  "src/lib/brand.ts", // the product's name, a proper noun with an accent
  "src/lib/error-page.ts", // renders when the framework cannot: its own two-language table
  "src/components/celestin/charts/format.ts", // the board's notation and the course's statistics words
];

/** `m.some_key()` called outside any function runs once, at import: on the server that is
 *  outside the request, so the language would be frozen. A table of message *functions*
 *  (`{ done: m.state_done }`, not called) is fine. */
export const noModuleScopeMessage = {
  meta: {
    type: "problem",
    schema: [],
    messages: {
      moduleScope:
        "Do not call a message function at module scope: it is evaluated once, outside the " +
        "request, and freezes the language. Call it inside a function, or keep the function " +
        "itself (m.some_key, not m.some_key()) in the table.",
    },
  },
  create(context) {
    return {
      CallExpression(node) {
        const callee = node.callee;
        if (
          callee.type !== "MemberExpression" ||
          callee.object.type !== "Identifier" ||
          callee.object.name !== "m"
        ) {
          return;
        }
        for (let parent = node.parent; parent; parent = parent.parent) {
          if (/Function/.test(parent.type)) return;
        }
        context.report({ node, messageId: "moduleScope" });
      },
    };
  },
};

export const i18nPlugin = { rules: { "no-module-scope-message": noModuleScopeMessage } };
