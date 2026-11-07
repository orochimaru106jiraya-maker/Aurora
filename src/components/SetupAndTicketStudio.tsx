import React, { useState } from 'react';
import {
  DEFAULT_FOUR_TICKET_CATEGORIES,
  SimulatedTicket,
  TicketCategorySpec,
  closeSimulatedTicket,
  evaluateModerationHierarchy,
  evaluateRbacMutation,
} from '../utils/botRules';

const FOURTEEN_SETUP_PAGES = [
  { key: 'overview', num: '01', title: 'Overview', summary: 'Bot status, SQLite WAL status, module toggles, and completion metrics.' },
  { key: 'moderation', num: '02', title: 'Moderation', summary: '19 moderation commands, role hierarchy enforcement, and snipe retention.' },
  { key: 'tickets', num: '03', title: 'Tickets', summary: '4 independent categories, custom forms, transcripts, and DM routing.' },
  { key: 'permissions', num: '04', title: 'Permissions', summary: 'Centralized RBAC engine, anti-escalation, and self-admin protection.' },
  { key: 'activity_roles', num: '05', title: 'Activity Roles', summary: 'Spotify, Gaming, Voice Chat, and Text Chat milestone roles.' },
  { key: 'reaction_roles', num: '06', title: 'Reaction Roles', summary: 'Persistent button, dropdown, and emoji reaction role panels.' },
  { key: 'jtc', num: '07', title: 'Join-to-Create', summary: 'Dynamic temporary voice hubs, ownership controls, and restart recovery.' },
  { key: 'music', num: '08', title: 'Music', summary: 'FFmpeg + PyNaCl audio streaming, track validation, loop, and DJ controls.' },
  { key: 'ai_assistant', num: '09', title: 'AI Assistant', summary: 'Zero-API-key Mode A Knowledge Base + Mode B Optional Local LLM.' },
  { key: 'auto_responder', num: '10', title: 'Auto Responder', summary: 'Exact and partial phrase matching, cooldowns, and channel filters.' },
  { key: 'embeds', num: '11', title: 'Embed Builder', summary: 'Interactive modal embed editor with reusable SQLite templates.' },
  { key: 'logging', num: '12', title: 'Logging', summary: 'Moderation case logs, server audit stream, and transcript archive channel.' },
  { key: 'administration', num: '13', title: 'Administration', summary: 'Command prefix, server settings, and health diagnostics.' },
  { key: 'database_backup', num: '14', title: 'DB & Backup', summary: 'SQLite schema v6 migrations and one-click JSON snapshot backups.' },
];

export const SetupAndTicketStudio: React.FC = () => {
  const [activeSetupPage, setActiveSetupPage] = useState<string>('tickets');
  const [selectedCatKey, setSelectedCatKey] = useState<string>('general_help');
  const [categories, setCategories] = useState<TicketCategorySpec[]>(DEFAULT_FOUR_TICKET_CATEGORIES);
  const [tickets, setTickets] = useState<SimulatedTicket[]>([
    {
      ticketNumber: 1,
      categoryKey: 'claim_prize',
      categoryName: 'Claim Winning Prize',
      channelName: 'prize-rohan-0001',
      creatorName: 'Rohan',
      creatorId: '501092',
      status: 'claimed',
      claimedBy: 'Mod_Aisha',
      formResponses: {
        'Event or Giveaway Name': 'Weekly Nitro Giveaway #14',
        'Winning Message Link / Proof': 'https://discord.com/channels/8080/9090/112233',
      },
      createdAt: '2026-11-07 10:12:00 UTC',
    },
  ]);

  const [newCreatorName, setNewCreatorName] = useState<string>('AlexDev');
  const [newFormAnswer, setNewFormAnswer] = useState<string>('Need assistance configuring JTC voice channel permissions.');
  const [closeReasonInput, setCloseReasonInput] = useState<string>('Issue resolved and verified with user');
  const [closingModInput, setClosingModInput] = useState<string>('Admin_Vikram');
  const [creatorDmToggle, setCreatorDmToggle] = useState<boolean>(true);
  const [ticketFeedback, setTicketFeedback] = useState<string>('');

  // RBAC & Hierarchy Interactive Simulator state
  const [actorLevel, setActorLevel] = useState<string>('moderator');
  const [actorId, setActorId] = useState<string>('3001');
  const [targetUserId, setTargetUserId] = useState<string>('3001');
  const [targetLevel, setTargetLevel] = useState<string>('administrator');
  const [rbacResult, setRbacResult] = useState<{ allowed: boolean; reason: string } | null>(null);

  const [modRolePos, setModRolePos] = useState<number>(20);
  const [targetRolePos, setTargetRolePos] = useState<number>(25);
  const [hierarchyResult, setHierarchyResult] = useState<{ allowed: boolean; reason: string } | null>(null);

  const currentCategory = categories.find((c) => c.key === selectedCatKey) || categories[0];
  const currentPageMeta = FOURTEEN_SETUP_PAGES.find((p) => p.key === activeSetupPage) || FOURTEEN_SETUP_PAGES[0];

  const handleOpenSimulatedTicket = (e: React.FormEvent) => {
    e.preventDefault();
    const cleanUser = newCreatorName.trim();
    const cleanAnswer = newFormAnswer.trim();
    if (!cleanUser || !cleanAnswer) {
      setTicketFeedback('Validation Error: Creator username and ticket form details are required.');
      return;
    }

    // Duplicate open ticket check per user & category
    const existingOpen = tickets.filter(
      (t) =>
        t.creatorName.toLowerCase() === cleanUser.toLowerCase() &&
        t.categoryKey === currentCategory.key &&
        t.status !== 'closed'
    );
    if (existingOpen.length >= currentCategory.maxOpenPerUser) {
      setTicketFeedback(
        `Duplicate Ticket Prevented: ${cleanUser} already has an active ${currentCategory.name} ticket (#${String(
          existingOpen[0].ticketNumber
        ).padStart(4, '0')}).`
      );
      return;
    }

    const nextNum = tickets.length + 1;
    const channelSlug = currentCategory.namingFormat
      .replace('{username}', cleanUser.toLowerCase().replace(/[^a-z0-9]/g, ''))
      .replace('{id}', String(nextNum).padStart(4, '0'));

    const created: SimulatedTicket = {
      ticketNumber: nextNum,
      categoryKey: currentCategory.key,
      categoryName: currentCategory.name,
      channelName: channelSlug,
      creatorName: cleanUser,
      creatorId: String(500000 + nextNum),
      status: 'open',
      formResponses: {
        [currentCategory.fields[0]?.label || 'Details']: cleanAnswer,
      },
      createdAt: new Date().toISOString().replace('T', ' ').slice(0, 19) + ' UTC',
    };

    setTickets([created, ...tickets]);
    setTicketFeedback(`Opened Ticket #${String(nextNum).padStart(4, '0')} in #${channelSlug} (${currentCategory.name}).`);
  };

  const handleClaimTicket = (ticketNum: number) => {
    setTickets((prev) =>
      prev.map((t) =>
        t.ticketNumber === ticketNum && t.status !== 'closed'
          ? { ...t, status: 'claimed', claimedBy: closingModInput.trim() || 'Mod_Aisha' }
          : t
      )
    );
    setTicketFeedback(`Ticket #${String(ticketNum).padStart(4, '0')} claimed by ${closingModInput || 'Mod_Aisha'}.`);
  };

  const handleUnclaimTicket = (ticketNum: number) => {
    setTickets((prev) =>
      prev.map((t) =>
        t.ticketNumber === ticketNum && t.status !== 'closed'
          ? { ...t, status: 'open', claimedBy: undefined }
          : t
      )
    );
    setTicketFeedback(`Ticket #${String(ticketNum).padStart(4, '0')} is now unclaimed.`);
  };

  const handleCloseTicket = (ticketNum: number) => {
    setTickets((prev) =>
      prev.map((t) =>
        t.ticketNumber === ticketNum && t.status !== 'closed'
          ? closeSimulatedTicket(
              t,
              closingModInput.trim() || 'Admin_Vikram',
              closeReasonInput.trim() || 'Resolved by staff',
              creatorDmToggle
            )
          : t
      )
    );
    setTicketFeedback(
      `Closed Ticket #${String(ticketNum).padStart(4, '0')}: Generated transcript, archived to #ticket-transcripts, and dispatched creator & moderator DMs.`
    );
  };

  const handleUpdateMaxOpen = (delta: number) => {
    setCategories((prev) =>
      prev.map((c) =>
        c.key === currentCategory.key
          ? { ...c, maxOpenPerUser: Math.max(1, Math.min(5, c.maxOpenPerUser + delta)) }
          : c
      )
    );
  };

  const handleRunRbacCheck = (e: React.FormEvent) => {
    e.preventDefault();
    const res = evaluateRbacMutation({
      actorId: actorId.trim(),
      actorLevel,
      targetUserId: targetUserId.trim(),
      targetLevel,
      serverOwnerId: '1001',
      botOwnerId: '9999',
    });
    setRbacResult(res);
  };

  const handleRunHierarchyCheck = (e: React.FormEvent) => {
    e.preventDefault();
    const res = evaluateModerationHierarchy({
      actorId: '3001',
      actorRolePosition: modRolePos,
      targetId: '4001',
      targetRolePosition: targetRolePos,
      botRolePosition: 50,
      serverOwnerId: '1001',
    });
    setHierarchyResult(res);
  };

  return (
    <div className="space-y-8">
      {/* 14-Page /setup Dashboard Explorer */}
      <section className="border border-slate-800 bg-slate-900/60 rounded-xl p-6">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 pb-6 border-b border-slate-800">
          <div>
            <h2 className="text-xl font-semibold text-slate-100">
              Interactive <code className="font-mono text-indigo-300">/setup</code> 14-Page Dashboard Simulator
            </h2>
            <p className="text-sm text-slate-400 mt-1">
              Inspect all 14 server management pages exposed by <code className="font-mono text-slate-300">SetupDashboardView</code> in <code className="font-mono text-slate-300">bot/ui/dashboard.py</code>.
            </p>
          </div>
          <div className="flex items-center gap-3 text-xs text-slate-400 font-mono tabular-nums">
            <span>Active Page: {currentPageMeta.num} / 14</span>
            <span aria-hidden="true">·</span>
            <span>Persistent Views: 4 Registered</span>
          </div>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-2 mt-5">
          {FOURTEEN_SETUP_PAGES.map((page) => {
            const isSelected = page.key === activeSetupPage;
            return (
              <button
                key={page.key}
                type="button"
                onClick={() => setActiveSetupPage(page.key)}
                className={`px-3 py-2 text-left rounded-lg border text-xs transition-colors whitespace-nowrap shrink-0 truncate ${
                  isSelected
                    ? 'bg-indigo-600 text-white border-indigo-500 font-semibold'
                    : 'bg-slate-950/70 text-slate-300 border-slate-800 hover:border-slate-700 hover:text-white'
                }`}
              >
                {page.num}. {page.title}
              </button>
            );
          })}
        </div>

        <div className="mt-5 p-4 rounded-lg border border-slate-800 bg-slate-950/80 flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="text-xs text-indigo-400 font-mono">
              /setup page:{currentPageMeta.key}
            </div>
            <h3 className="text-base font-semibold text-slate-100 mt-0.5">
              {currentPageMeta.num}. {currentPageMeta.title} Configuration Panel
            </h3>
            <p className="text-sm text-slate-400 mt-1">{currentPageMeta.summary}</p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <button
              type="button"
              onClick={() => {
                const idx = FOURTEEN_SETUP_PAGES.findIndex((p) => p.key === activeSetupPage);
                const prev = FOURTEEN_SETUP_PAGES[(idx - 1 + FOURTEEN_SETUP_PAGES.length) % FOURTEEN_SETUP_PAGES.length];
                setActiveSetupPage(prev.key);
              }}
              className="px-3 py-1.5 text-xs font-medium text-slate-200 bg-slate-900 border border-slate-700 rounded-lg hover:bg-slate-800 whitespace-nowrap shrink-0"
            >
              Previous Page
            </button>
            <button
              type="button"
              onClick={() => setActiveSetupPage('overview')}
              className="px-3 py-1.5 text-xs font-medium text-slate-200 bg-slate-900 border border-slate-700 rounded-lg hover:bg-slate-800 whitespace-nowrap shrink-0"
            >
              Overview
            </button>
            <button
              type="button"
              onClick={() => {
                const idx = FOURTEEN_SETUP_PAGES.findIndex((p) => p.key === activeSetupPage);
                const next = FOURTEEN_SETUP_PAGES[(idx + 1) % FOURTEEN_SETUP_PAGES.length];
                setActiveSetupPage(next.key);
              }}
              className="px-3 py-1.5 text-xs font-medium text-white bg-indigo-600 rounded-lg hover:bg-indigo-500 whitespace-nowrap shrink-0"
            >
              Next Page
            </button>
          </div>
        </div>
      </section>

      {/* 4-Category Ticket System & Closing Pipeline Simulator */}
      <section className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-stretch">
        <div className="lg:col-span-5 border border-slate-800 bg-slate-900/60 rounded-xl p-6 flex flex-col justify-between">
          <div>
            <h2 className="text-lg font-semibold text-slate-100">
              1. 4-Category <code className="font-mono text-indigo-300">/jticket</code> Panel & Form Builder
            </h2>
            <p className="text-sm text-slate-400 mt-1">
              Select any of the 4 default categories to configure limits or test duplicate-protected ticket creation.
            </p>

            <div className="grid grid-cols-2 gap-2 mt-4">
              {categories.map((cat) => (
                <button
                  key={cat.key}
                  type="button"
                  onClick={() => setSelectedCatKey(cat.key)}
                  className={`px-3 py-2.5 rounded-lg border text-left text-xs font-medium transition-colors whitespace-nowrap shrink-0 truncate ${
                    cat.key === selectedCatKey
                      ? 'bg-indigo-600/20 border-indigo-500 text-indigo-200'
                      : 'bg-slate-950/60 border-slate-800 text-slate-300 hover:border-slate-700'
                  }`}
                >
                  {cat.emoji} {cat.name}
                </button>
              ))}
            </div>

            <div className="mt-4 p-4 rounded-lg border border-slate-800 bg-slate-950/60 space-y-2 text-xs">
              <div className="flex items-center justify-between text-slate-300">
                <span>Category Key:</span>
                <span className="font-mono text-indigo-300">{currentCategory.key}</span>
              </div>
              <div className="flex items-center justify-between text-slate-300">
                <span>Channel Naming Pattern:</span>
                <span className="font-mono text-slate-200">{currentCategory.namingFormat}</span>
              </div>
              <div className="flex items-center justify-between text-slate-300">
                <span>Authorized Staff Role:</span>
                <span className="font-mono text-slate-200">@{currentCategory.staffRoleName}</span>
              </div>
              <div className="flex items-center justify-between text-slate-300">
                <span>Max Open Tickets / User:</span>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    aria-label="Decrease max open tickets"
                    onClick={() => handleUpdateMaxOpen(-1)}
                    className="px-2 py-0.5 bg-slate-800 rounded text-slate-200 hover:bg-slate-700"
                  >
                    -
                  </button>
                  <span className="font-mono tabular-nums font-semibold">{currentCategory.maxOpenPerUser}</span>
                  <button
                    type="button"
                    aria-label="Increase max open tickets"
                    onClick={() => handleUpdateMaxOpen(1)}
                    className="px-2 py-0.5 bg-slate-800 rounded text-slate-200 hover:bg-slate-700"
                  >
                    +
                  </button>
                </div>
              </div>
            </div>

            <form onSubmit={handleOpenSimulatedTicket} className="mt-4 space-y-3">
              <div>
                <label htmlFor="ticket-creator-input" className="block text-xs font-medium text-slate-300 mb-1">
                  Ticket Creator Username
                </label>
                <input
                  id="ticket-creator-input"
                  type="text"
                  value={newCreatorName}
                  onChange={(e) => setNewCreatorName(e.target.value)}
                  className="w-full px-3 py-2 text-sm bg-slate-950 border border-slate-800 rounded-lg text-slate-100 focus:outline-none focus:border-indigo-500"
                  placeholder="e.g. AlexDev"
                />
              </div>
              <div>
                <label htmlFor="ticket-form-input" className="block text-xs font-medium text-slate-300 mb-1">
                  {currentCategory.fields[0]?.label || 'Ticket Intake Details'}
                </label>
                <textarea
                  id="ticket-form-input"
                  rows={2}
                  value={newFormAnswer}
                  onChange={(e) => setNewFormAnswer(e.target.value)}
                  className="w-full px-3 py-2 text-sm bg-slate-950 border border-slate-800 rounded-lg text-slate-100 focus:outline-none focus:border-indigo-500"
                  placeholder={currentCategory.fields[0]?.placeholder}
                />
              </div>
              <button
                type="submit"
                className="w-full py-2 px-4 text-xs font-semibold text-white bg-indigo-600 rounded-lg hover:bg-indigo-500 transition-colors whitespace-nowrap shrink-0"
              >
                Open {currentCategory.name} Ticket
              </button>
            </form>
          </div>

          {ticketFeedback && (
            <div className="mt-4 p-3 rounded-lg border border-slate-700 bg-slate-950 text-xs text-slate-200">
              {ticketFeedback}
            </div>
          )}
        </div>

        {/* Active & Closed Ticket Lifecycle + Transcript & DM Inspector */}
        <div className="lg:col-span-7 border border-slate-800 bg-slate-900/60 rounded-xl p-6 flex flex-col justify-between">
          <div>
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-4 border-b border-slate-800">
              <div>
                <h2 className="text-lg font-semibold text-slate-100">
                  2. Ticket Claim, Transcript & Dual-DM Closing Pipeline
                </h2>
                <p className="text-xs text-slate-400 mt-0.5">
                  Closing a ticket generates a full transcript, archives it, DMs the creator, and DMs the claiming (or closing) moderator.
                </p>
              </div>
              <span className="text-xs font-mono text-slate-400 tabular-nums shrink-0">
                Total: {tickets.length} Tickets
              </span>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mt-4">
              <div>
                <label htmlFor="closing-mod-input" className="block text-xs text-slate-400 mb-1">
                  Acting Staff / Moderator
                </label>
                <input
                  id="closing-mod-input"
                  type="text"
                  value={closingModInput}
                  onChange={(e) => setClosingModInput(e.target.value)}
                  className="w-full px-2.5 py-1.5 text-xs bg-slate-950 border border-slate-800 rounded-lg text-slate-100"
                />
              </div>
              <div>
                <label htmlFor="closing-reason-input" className="block text-xs text-slate-400 mb-1">
                  Closing Reason
                </label>
                <input
                  id="closing-reason-input"
                  type="text"
                  value={closeReasonInput}
                  onChange={(e) => setCloseReasonInput(e.target.value)}
                  className="w-full px-2.5 py-1.5 text-xs bg-slate-950 border border-slate-800 rounded-lg text-slate-100"
                />
              </div>
              <div className="flex items-end pb-1">
                <label className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer select-none">
                  <input
                    type="checkbox"
                    checked={creatorDmToggle}
                    onChange={(e) => setCreatorDmToggle(e.target.checked)}
                    className="rounded border-slate-700 bg-slate-950 text-indigo-600"
                  />
                  <span>Creator Allows DMs</span>
                </label>
              </div>
            </div>

            <div className="mt-4 space-y-3 max-h-96 overflow-y-auto pr-1">
              {tickets.map((t) => (
                <div
                  key={t.ticketNumber}
                  className="p-4 rounded-lg border border-slate-800 bg-slate-950/80 space-y-2"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-2 text-xs">
                      <span className="font-mono font-semibold text-indigo-400 tabular-nums">
                        #{String(t.ticketNumber).padStart(4, '0')}
                      </span>
                      <span aria-hidden="true" className="text-slate-600">·</span>
                      <span className="font-mono text-slate-200">#{t.channelName}</span>
                      <span aria-hidden="true" className="text-slate-600">·</span>
                      <span className="text-slate-300">{t.categoryName}</span>
                    </div>
                    <div className="text-xs font-mono text-slate-400">
                      Status: <strong className="text-slate-100 uppercase">{t.status}</strong> · Claimed:{' '}
                      <span className="text-indigo-300">{t.claimedBy || 'Unclaimed'}</span>
                    </div>
                  </div>

                  <div className="text-xs text-slate-400">
                    Creator: <span className="text-slate-200">{t.creatorName}</span> ({t.creatorId}) · Created: {t.createdAt}
                  </div>

                  {t.status !== 'closed' ? (
                    <div className="flex flex-wrap items-center gap-2 pt-1">
                      <button
                        type="button"
                        onClick={() => handleClaimTicket(t.ticketNumber)}
                        className="px-3 py-1 text-xs font-medium text-slate-100 bg-slate-800 rounded hover:bg-slate-700 whitespace-nowrap shrink-0"
                      >
                        Claim Ticket #{t.ticketNumber}
                      </button>
                      <button
                        type="button"
                        onClick={() => handleUnclaimTicket(t.ticketNumber)}
                        className="px-3 py-1 text-xs font-medium text-slate-300 bg-slate-900 border border-slate-700 rounded hover:bg-slate-800 whitespace-nowrap shrink-0"
                      >
                        Unclaim Ticket #{t.ticketNumber}
                      </button>
                      <button
                        type="button"
                        onClick={() => handleCloseTicket(t.ticketNumber)}
                        className="px-3 py-1 text-xs font-medium text-white bg-rose-600 rounded hover:bg-rose-500 whitespace-nowrap shrink-0"
                      >
                        Close & Dispatch DMs #{t.ticketNumber}
                      </button>
                    </div>
                  ) : (
                    <div className="pt-2 border-t border-slate-800/80 space-y-2 text-xs">
                      <div className="text-emerald-400 font-mono">
                        Creator DM: {t.dmCreatorDelivered ? 'Delivered' : 'Fallback (Creator DMs Closed)'} · Staff DM (
                        {t.notifiedStaffName}): Delivered · Reason: {t.closeReason}
                      </div>
                      {t.transcript && (
                        <pre className="p-2.5 rounded bg-slate-900 border border-slate-800 text-[11px] text-slate-300 overflow-x-auto font-mono">
                          {t.transcript}
                        </pre>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* Server-Side RBAC & Role Hierarchy Security Evaluators */}
      <section className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="border border-slate-800 bg-slate-900/60 rounded-xl p-6">
          <h3 className="text-base font-semibold text-slate-100">
            3. RBAC Anti-Escalation & Self-Admin Guard (<code className="font-mono text-indigo-300">PermissionService</code>)
          </h3>
          <p className="text-xs text-slate-400 mt-1">
            Verify that users cannot grant themselves <code className="font-mono text-slate-300">administrator</code> or assign permission levels equal to or above their own.
          </p>

          <form onSubmit={handleRunRbacCheck} className="mt-4 grid grid-cols-2 gap-3">
            <div>
              <label htmlFor="rbac-actor-level" className="block text-xs text-slate-300 mb-1">
                Actor Effective Level
              </label>
              <select
                id="rbac-actor-level"
                value={actorLevel}
                onChange={(e) => setActorLevel(e.target.value)}
                className="w-full px-2.5 py-1.5 text-xs bg-slate-950 border border-slate-800 rounded-lg text-slate-100"
              >
                <option value="moderator">moderator (50)</option>
                <option value="administrator">administrator (80)</option>
                <option value="server_owner">server_owner (90)</option>
              </select>
            </div>
            <div>
              <label htmlFor="rbac-target-level" className="block text-xs text-slate-300 mb-1">
                Permission Level to Grant
              </label>
              <select
                id="rbac-target-level"
                value={targetLevel}
                onChange={(e) => setTargetLevel(e.target.value)}
                className="w-full px-2.5 py-1.5 text-xs bg-slate-950 border border-slate-800 rounded-lg text-slate-100"
              >
                <option value="music_dj">music_dj (10)</option>
                <option value="ticket_staff">ticket_staff (20)</option>
                <option value="moderator">moderator (50)</option>
                <option value="administrator">administrator (80)</option>
              </select>
            </div>
            <div>
              <label htmlFor="rbac-actor-id" className="block text-xs text-slate-300 mb-1">
                Actor User ID
              </label>
              <input
                id="rbac-actor-id"
                type="text"
                value={actorId}
                onChange={(e) => setActorId(e.target.value)}
                className="w-full px-2.5 py-1.5 text-xs bg-slate-950 border border-slate-800 rounded-lg text-slate-100 font-mono"
              />
            </div>
            <div>
              <label htmlFor="rbac-target-id" className="block text-xs text-slate-300 mb-1">
                Target User ID (9999 = Bot Owner)
              </label>
              <input
                id="rbac-target-id"
                type="text"
                value={targetUserId}
                onChange={(e) => setTargetUserId(e.target.value)}
                className="w-full px-2.5 py-1.5 text-xs bg-slate-950 border border-slate-800 rounded-lg text-slate-100 font-mono"
              />
            </div>
            <div className="col-span-2">
              <button
                type="submit"
                className="w-full py-2 px-4 text-xs font-semibold text-white bg-indigo-600 rounded-lg hover:bg-indigo-500 whitespace-nowrap shrink-0"
              >
                Test RBAC Permission Mutation
              </button>
            </div>
          </form>

          {rbacResult && (
            <div
              className={`mt-3 p-3 rounded-lg border text-xs font-mono ${
                rbacResult.allowed
                  ? 'border-emerald-700/60 bg-emerald-950/30 text-emerald-300'
                  : 'border-rose-700/60 bg-rose-950/30 text-rose-300'
              }`}
            >
              [{rbacResult.allowed ? 'ALLOWED' : 'BLOCKED'}] {rbacResult.reason}
            </div>
          )}
        </div>

        <div className="border border-slate-800 bg-slate-900/60 rounded-xl p-6">
          <h3 className="text-base font-semibold text-slate-100">
            4. Moderation Role Hierarchy Guard (<code className="font-mono text-indigo-300">validate_role_hierarchy</code>)
          </h3>
          <p className="text-xs text-slate-400 mt-1">
            No moderator can ban, kick, warn, or timeout a member with an equal or higher top role position.
          </p>

          <form onSubmit={handleRunHierarchyCheck} className="mt-4 grid grid-cols-2 gap-3">
            <div>
              <label htmlFor="mod-role-pos" className="block text-xs text-slate-300 mb-1">
                Moderator Top Role Position
              </label>
              <input
                id="mod-role-pos"
                type="number"
                value={modRolePos}
                onChange={(e) => setModRolePos(Number(e.target.value))}
                className="w-full px-2.5 py-1.5 text-xs bg-slate-950 border border-slate-800 rounded-lg text-slate-100 font-mono tabular-nums"
              />
            </div>
            <div>
              <label htmlFor="target-role-pos" className="block text-xs text-slate-300 mb-1">
                Target Member Top Role Position
              </label>
              <input
                id="target-role-pos"
                type="number"
                value={targetRolePos}
                onChange={(e) => setTargetRolePos(Number(e.target.value))}
                className="w-full px-2.5 py-1.5 text-xs bg-slate-950 border border-slate-800 rounded-lg text-slate-100 font-mono tabular-nums"
              />
            </div>
            <div className="col-span-2">
              <button
                type="submit"
                className="w-full py-2 px-4 text-xs font-semibold text-white bg-indigo-600 rounded-lg hover:bg-indigo-500 whitespace-nowrap shrink-0"
              >
                Verify Role Hierarchy Check
              </button>
            </div>
          </form>

          {hierarchyResult && (
            <div
              className={`mt-3 p-3 rounded-lg border text-xs font-mono ${
                hierarchyResult.allowed
                  ? 'border-emerald-700/60 bg-emerald-950/30 text-emerald-300'
                  : 'border-rose-700/60 bg-rose-950/30 text-rose-300'
              }`}
            >
              [{hierarchyResult.allowed ? 'ALLOWED' : 'BLOCKED'}] {hierarchyResult.reason}
            </div>
          )}
        </div>
      </section>
    </div>
  );
};
