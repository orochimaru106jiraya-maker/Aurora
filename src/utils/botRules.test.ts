import test from 'node:test';
import assert from 'node:assert/strict';
import {
  DEFAULT_FOUR_TICKET_CATEGORIES,
  closeSimulatedTicket,
  evaluateModerationHierarchy,
  evaluateRbacMutation,
  filterCommandRegistry,
  SlashCommandEntry,
} from './botRules';

const SAMPLE_COMMANDS: SlashCommandEntry[] = [
  {
    qualified_name: '/jticket setup',
    name: 'setup',
    group: 'jticket',
    cog: 'TicketsCog',
    description: 'Launch the interactive Ticket System Setup Dashboard for all 4 categories.',
  },
  {
    qualified_name: '/permissions role add',
    name: 'add',
    group: 'permissions role',
    cog: 'PermissionsCog',
    description: 'Grant an RBAC permission level to a Discord role.',
  },
  {
    qualified_name: '/ban',
    name: 'ban',
    group: 'root',
    cog: 'ModerationCog',
    description: 'Ban a member from the server with hierarchy protection and case logging.',
  },
];

test('DEFAULT_FOUR_TICKET_CATEGORIES defines all 4 required ticket categories', () => {
  assert.equal(DEFAULT_FOUR_TICKET_CATEGORIES.length, 4);
  const keys = DEFAULT_FOUR_TICKET_CATEGORIES.map((c) => c.key);
  assert.deepEqual(keys, ['general_help', 'file_complaint', 'staff_application', 'claim_prize']);
});

test('filterCommandRegistry filters by search query and cog filter accurately', () => {
  const byQuery = filterCommandRegistry(SAMPLE_COMMANDS, 'jticket', 'all');
  assert.equal(byQuery.length, 1);
  assert.equal(byQuery[0].qualified_name, '/jticket setup');

  const byCog = filterCommandRegistry(SAMPLE_COMMANDS, '', 'PermissionsCog');
  assert.equal(byCog.length, 1);
  assert.equal(byCog[0].qualified_name, '/permissions role add');
});

test('evaluateRbacMutation blocks self-admin grants and privilege escalation', () => {
  const selfAdmin = evaluateRbacMutation({
    actorId: '2001',
    actorLevel: 'administrator',
    targetUserId: '2001',
    targetLevel: 'administrator',
    serverOwnerId: '1001',
    botOwnerId: '9999',
  });
  assert.equal(selfAdmin.allowed, false);
  assert.match(selfAdmin.reason, /cannot grant themselves Administrator/);

  const modEscalation = evaluateRbacMutation({
    actorId: '3001',
    actorLevel: 'moderator',
    targetUserId: '4001',
    targetLevel: 'administrator',
    serverOwnerId: '1001',
    botOwnerId: '9999',
  });
  assert.equal(modEscalation.allowed, false);
  assert.match(modEscalation.reason, /Privilege Escalation Blocked/);

  const validGrant = evaluateRbacMutation({
    actorId: '2001',
    actorLevel: 'administrator',
    targetUserId: '4001',
    targetLevel: 'ticket_staff',
    serverOwnerId: '1001',
    botOwnerId: '9999',
  });
  assert.equal(validGrant.allowed, true);
});

test('evaluateModerationHierarchy blocks equal or higher role targets', () => {
  const equalRole = evaluateModerationHierarchy({
    actorId: '3001',
    actorRolePosition: 20,
    targetId: '3002',
    targetRolePosition: 20,
    botRolePosition: 50,
    serverOwnerId: '1001',
  });
  assert.equal(equalRole.allowed, false);

  const lowerRole = evaluateModerationHierarchy({
    actorId: '3001',
    actorRolePosition: 20,
    targetId: '4001',
    targetRolePosition: 5,
    botRolePosition: 50,
    serverOwnerId: '1001',
  });
  assert.equal(lowerRole.allowed, true);
});

test('closeSimulatedTicket notifies claiming moderator or falls back to closing moderator', () => {
  const claimedTicket = closeSimulatedTicket(
    {
      ticketNumber: 1,
      categoryKey: 'claim_prize',
      categoryName: 'Claim Winning Prize',
      channelName: 'prize-alice-0001',
      creatorName: 'Alice',
      creatorId: '5001',
      status: 'claimed',
      claimedBy: 'Mod_Bob',
      formResponses: { Event: 'Nitro Giveaway #14' },
      createdAt: '2026-11-07T10:00:00Z',
    },
    'Admin_Charlie',
    'Prize verified and delivered',
    true
  );

  assert.equal(claimedTicket.status, 'closed');
  assert.equal(claimedTicket.notifiedStaffName, 'Mod_Bob');
  assert.equal(claimedTicket.dmCreatorDelivered, true);
  assert.equal(claimedTicket.dmStaffDelivered, true);
  assert.ok(claimedTicket.transcript?.includes('COSMIC KI BADDIE (AURORA)'));

  const unclaimedTicket = closeSimulatedTicket(
    {
      ticketNumber: 2,
      categoryKey: 'general_help',
      categoryName: 'General Help',
      channelName: 'help-bob-0002',
      creatorName: 'Bob',
      creatorId: '5002',
      status: 'open',
      formResponses: { Question: 'How to join voice?' },
      createdAt: '2026-11-07T10:05:00Z',
    },
    'Admin_Charlie',
    'Answered question',
    false
  );
  assert.equal(unclaimedTicket.notifiedStaffName, 'Admin_Charlie');
  assert.equal(unclaimedTicket.dmCreatorDelivered, false);
});
