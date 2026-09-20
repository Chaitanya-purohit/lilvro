-- Demo parent + child + sample activity for local dashboard.
-- Password for parent@lilvro.local: password123
-- Fixed UUIDs so root .env CHILD_ID can point at the seeded child.

create extension if not exists "pgcrypto";

-- Auth user (local only; enable_confirmations = false in config.toml)
insert into auth.users (
  instance_id,
  id,
  aud,
  role,
  email,
  encrypted_password,
  email_confirmed_at,
  raw_app_meta_data,
  raw_user_meta_data,
  created_at,
  updated_at
) values (
  '00000000-0000-0000-0000-000000000000',
  'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
  'authenticated',
  'authenticated',
  'parent@lilvro.local',
  crypt('password123', gen_salt('bf')),
  now(),
  '{"provider":"email","providers":["email"]}'::jsonb,
  '{"display_name":"Demo Parent"}'::jsonb,
  now(),
  now()
) on conflict (id) do nothing;

-- identity for email login
insert into auth.identities (
  id,
  user_id,
  identity_data,
  provider,
  provider_id,
  last_sign_in_at,
  created_at,
  updated_at
) values (
  'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
  'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
  jsonb_build_object('sub', 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', 'email', 'parent@lilvro.local'),
  'email',
  'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
  now(),
  now(),
  now()
) on conflict (id) do nothing;

-- Profile may already exist via trigger; ensure it
insert into public.profiles (id, role, display_name)
values ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', 'parent', 'Demo Parent')
on conflict (id) do update set display_name = excluded.display_name;

insert into public.children (id, parent_id, display_name)
values (
  'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
  'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
  'Alex'
) on conflict (id) do nothing;

insert into public.devices (id, child_id, label)
values (
  'cccccccc-cccc-cccc-cccc-cccccccccccc',
  'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
  'local-dev'
) on conflict (id) do nothing;

insert into public.child_stats (
  child_id, current_streak_days, longest_streak_days, sessions_completed, last_session_on
) values (
  'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', 3, 5, 4, current_date
) on conflict (child_id) do update set
  current_streak_days = excluded.current_streak_days,
  longest_streak_days = excluded.longest_streak_days,
  sessions_completed = excluded.sessions_completed,
  last_session_on = excluded.last_session_on;

insert into public.sessions (
  id, child_id, started_at, ended_at, turn_count, primary_mode, topic, duration_seconds
) values (
  'dddddddd-dddd-dddd-dddd-dddddddddddd',
  'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
  now() - interval '1 day',
  now() - interval '1 day' + interval '12 minutes',
  4,
  'walkthrough',
  'fractions',
  720
) on conflict (id) do nothing;

insert into public.turns (session_id, idx, role, content, mode, topic) values
  ('dddddddd-dddd-dddd-dddd-dddddddddddd', 0, 'user',
   'Can you help me with one half plus one fourth?', 'walkthrough', 'fractions'),
  ('dddddddd-dddd-dddd-dddd-dddddddddddd', 1, 'assistant',
   'Sure! What do both fractions need before we can add them?', 'walkthrough', 'fractions'),
  ('dddddddd-dddd-dddd-dddd-dddddddddddd', 2, 'user',
   'A common denominator?', 'walkthrough', 'fractions'),
  ('dddddddd-dddd-dddd-dddd-dddddddddddd', 3, 'assistant',
   'Exactly. What common denominator works for 2 and 4?', 'walkthrough', 'fractions')
on conflict (session_id, idx) do nothing;

insert into public.mastery_scores (child_id, topic, score, updated_at) values
  ('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', 'fractions', 0.62, now()),
  ('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', 'decimals', 0.41, now()),
  ('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', 'area', 0.28, now())
on conflict (child_id, topic) do update set
  score = excluded.score,
  updated_at = excluded.updated_at;

insert into public.mastery_events (child_id, session_id, event, topic, score) values
  ('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
   'dddddddd-dddd-dddd-dddd-dddddddddddd',
   'check_ok', 'fractions', 0.62);
