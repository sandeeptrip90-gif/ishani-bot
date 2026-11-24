export const MODERATION_TOGGLES = [
  {
    key: "link_removal",
    label: "Auto-remove links",
    description: "Delete link posts and inline buttons from non-admin members.",
  },
  {
    key: "abuse_removal",
    label: "Remove abuse / threats",
    description: "Delete abusive or threatening posts and answer calmly in the group.",
  },
  {
    key: "fraud_removal",
    label: "Handle fraud claims",
    description: "Remove fraud or scam allegations and clarify the facts in the group.",
  },
  {
    key: "bot_removal",
    label: "Ban non-admin bots",
    description: "Ban and remove bots that are not administrators of this group.",
  },
] as const;

export const MODERATION_DEFAULTS: Record<string, boolean> = {
  link_removal: true,
  abuse_removal: true,
  fraud_removal: true,
  bot_removal: true,
};
