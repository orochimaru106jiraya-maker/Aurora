/**
 * Pure domain logic for Cosmic ki baddie (Project Aurora) Control Plane & Sandbox Simulator.
 * Decoupled for deterministic unit testing with `node:test`.
 */

export interface SlashCommandEntry {
  qualified_name: string;
  name: string;
  group: string;
  cog: string;
  description: string;
}

export interface TicketCategorySpec {
  key: string;
  name: string;
  emoji: string;
  description: string;
  namingFormat: string;
  maxOpenPerUser: number;
  autoDeleteSeconds: number;
  staffRoleName: string;
  fields: Array<{ label: string; placeholder: string; required: boolean }>;
}

export interface SimulatedTicket {
  ticketNumber: number;
  categoryKey: string;
  categoryName: string;
  channelName: string;
  creatorName: string;
  creatorId: string;
  status: 'open' | 'claimed' | 'closed';
  claimedBy?: string;
  closedBy?: string;
  closeReason?: string;
  formResponses: Record<string, string>;
  transcript?: string;
  dmCreatorDelivered?: boolean;
  dmStaffDelivered?: boolean;
  notifiedStaffName?: string;
  createdAt: string;
  closedAt?: string;
}

export const ROLE_LEVEL_SCORES: Record<string, number> = {
  everyone: 0,
  music_dj: 10,
  ticket_staff: 20,
  support_team: 30,
  moderator: 50,
  administrator: 80,
  server_owner: 90,
  bot_owner: 100,
};

export const DEFAULT_FOUR_TICKET_CATEGORIES: TicketCategorySpec[] = [
  {
    key: 'general_help',
    name: 'General Help',
    emoji: '🛟',
    description: 'Get assistance with server rules, channels, roles, or general questions.',
    namingFormat: 'help-{username}-{id}',
    maxOpenPerUser: 1,
    autoDeleteSeconds: 300,
    staffRoleName: 'Support Team',
    fields: [
      { label: 'How can we help you?', placeholder: 'Describe your question or issue...', required: true },
      { label: 'Relevant Channel or User', placeholder: '#general or @username', required: false },
    ],
  },
  {
    key: 'file_complaint',
    name: 'File a Complaint',
    emoji: '⚖️',
    description: 'Report rule violations, harassment, or staff misconduct confidentially.',
    namingFormat: 'complaint-{username}-{id}',
    maxOpenPerUser: 1,
    autoDeleteSeconds: 600,
    staffRoleName: 'Senior Moderator',
    fields: [
      { label: 'Reported User(s) & ID', placeholder: 'Username / User ID', required: true },
      { label: 'Incident Description & Evidence', placeholder: 'Provide timestamps, links, and context...', required: true },
    ],
  },
  {
    key: 'staff_application',
    name: 'Apply for a Staff Role',
    emoji: '🛡️',
    description: 'Submit an application to join our moderation or support team.',
    namingFormat: 'apply-{username}-{id}',
    maxOpenPerUser: 1,
    autoDeleteSeconds: 600,
    staffRoleName: 'Server Administrator',
    fields: [
      { label: 'Desired Role & Timezone', placeholder: 'e.g., Moderator / UTC-5', required: true },
      { label: 'Previous Moderation Experience', placeholder: 'List servers, sizes, and responsibilities...', required: true },
      { label: 'Weekly Availability (Hours)', placeholder: 'e.g., 15-20 hours/week', required: true },
    ],
  },
  {
    key: 'claim_prize',
    name: 'Claim Winning Prize',
    emoji: '🏆',
    description: 'Verify and claim rewards from server giveaways, events, or tournaments.',
    namingFormat: 'prize-{username}-{id}',
    maxOpenPerUser: 1,
    autoDeleteSeconds: 300,
    staffRoleName: 'Event Coordinator',
    fields: [
      { label: 'Event or Giveaway Name', placeholder: 'Weekly Nitro Giveaway #14', required: true },
      { label: 'Winning Message Link / Proof', placeholder: 'Paste message link or details...', required: true },
    ],
  },
];

export function filterCommandRegistry(
  commands: SlashCommandEntry[],
  searchQuery: string,
  cogFilter: string
): SlashCommandEntry[] {
  const q = searchQuery.trim().toLowerCase();
  const c = cogFilter.trim().toLowerCase();

  return commands.filter((cmd) => {
    const matchesCog = !c || c === 'all' || cmd.cog.toLowerCase().includes(c);
    const matchesQuery =
      !q ||
      cmd.qualified_name.toLowerCase().includes(q) ||
      cmd.description.toLowerCase().includes(q) ||
      cmd.cog.toLowerCase().includes(q);
    return matchesCog && matchesQuery;
  });
}

export function evaluateRbacMutation(params: {
  actorId: string;
  actorLevel: string;
  targetUserId: string;
  targetLevel: string;
  serverOwnerId: string;
  botOwnerId: string;
}): { allowed: boolean; reason: string } {
  const { actorId, actorLevel, targetUserId, targetLevel, serverOwnerId, botOwnerId } = params;

  if (!(targetLevel in ROLE_LEVEL_SCORES)) {
    return { allowed: false, reason: `Unknown permission level: ${targetLevel}` };
  }
  if (targetLevel === 'bot_owner' || targetLevel === 'server_owner') {
    return { allowed: false, reason: 'Reserved owner levels cannot be granted via RBAC.' };
  }
  if (actorId === targetUserId && targetLevel === 'administrator') {
    return {
      allowed: false,
      reason: 'Security Policy Violation: Users cannot grant themselves Administrator permissions.',
    };
  }
  if (targetUserId === botOwnerId || targetUserId === serverOwnerId) {
    return {
      allowed: false,
      reason: 'Owner Protection: Cannot modify permissions of the Server Owner or Bot Owner.',
    };
  }

  const actorScore = ROLE_LEVEL_SCORES[actorLevel] ?? 0;
  const targetScore = ROLE_LEVEL_SCORES[targetLevel] ?? 0;
  if (actorLevel !== 'bot_owner' && actorLevel !== 'server_owner' && targetScore >= actorScore) {
    return {
      allowed: false,
      reason: `Privilege Escalation Blocked: Actor (${actorLevel}) cannot grant equal or higher level (${targetLevel}).`,
    };
  }

  return { allowed: true, reason: `Authorized: Granted ${targetLevel} to User ${targetUserId}.` };
}

export function evaluateModerationHierarchy(params: {
  actorId: string;
  actorRolePosition: number;
  targetId: string;
  targetRolePosition: number;
  botRolePosition: number;
  serverOwnerId: string;
}): { allowed: boolean; reason: string } {
  const { actorId, actorRolePosition, targetId, targetRolePosition, botRolePosition, serverOwnerId } = params;

  if (actorId === targetId) {
    return { allowed: false, reason: 'You cannot execute a moderation action on yourself.' };
  }
  if (targetId === serverOwnerId) {
    return { allowed: false, reason: 'Hierarchy Protection: Cannot moderate the Server Owner.' };
  }
  if (actorId !== serverOwnerId && actorRolePosition <= targetRolePosition) {
    return {
      allowed: false,
      reason: `Hierarchy Protection: Target role position (${targetRolePosition}) is equal to or higher than your role position (${actorRolePosition}).`,
    };
  }
  if (botRolePosition <= targetRolePosition) {
    return {
      allowed: false,
      reason: `Bot Hierarchy Protection: Target role position (${targetRolePosition}) is equal to or higher than Cosmic ki baddie's role (${botRolePosition}).`,
    };
  }
  return { allowed: true, reason: 'Hierarchy validation passed.' };
}

export function closeSimulatedTicket(
  ticket: SimulatedTicket,
  closingModeratorName: string,
  closeReason: string,
  creatorAllowsDm = true
): SimulatedTicket {
  const notifiedStaff = ticket.claimedBy || closingModeratorName;
  const closedAt = new Date().toISOString();
  const formLines = Object.entries(ticket.formResponses)
    .map(([k, v]) => `  • ${k}: ${v}`)
    .join('\n');

  const transcript = [
    '================================================================================',
    `COSMIC KI BADDIE (AURORA) — OFFICIAL TICKET TRANSCRIPT #${String(ticket.ticketNumber).padStart(4, '0')}`,
    '================================================================================',
    `Ticket ID:        #${String(ticket.ticketNumber).padStart(4, '0')}`,
    `Category:         ${ticket.categoryName} (${ticket.categoryKey})`,
    `Ticket Creator:   ${ticket.creatorName} (${ticket.creatorId})`,
    `Claimed By:       ${ticket.claimedBy ?? 'Unclaimed (Routed to closer)'}`,
    `Closed By:        ${closingModeratorName}`,
    `Notified Staff:   ${notifiedStaff}`,
    `Closing Reason:   ${closeReason}`,
    `Created At:       ${ticket.createdAt}`,
    `Closed At:        ${closedAt}`,
    '--------------------------------------------------------------------------------',
    'SUBMITTED FORM RESPONSES:',
    formLines || '  (None)',
    '================================================================================',
  ].join('\n');

  return {
    ...ticket,
    status: 'closed',
    closedBy: closingModeratorName,
    closeReason,
    closedAt,
    transcript,
    dmCreatorDelivered: creatorAllowsDm,
    dmStaffDelivered: true,
    notifiedStaffName: notifiedStaff,
  };
}
