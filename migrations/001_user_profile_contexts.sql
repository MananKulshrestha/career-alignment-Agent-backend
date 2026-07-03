create table if not exists user_profile_contexts (
  id uuid primary key,
  user_id uuid not null unique,
  abstract text,
  specializations jsonb not null default '[]'::jsonb,
  career_goals jsonb not null default '[]'::jsonb,
  target_roles jsonb not null default '[]'::jsonb,
  resume_strictness text not null default 'balanced'
    check (resume_strictness in ('conservative', 'balanced', 'assertive')),
  tone_preferences jsonb not null default '[]'::jsonb,
  avoid_claims jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists ix_user_profile_contexts_user_id
  on user_profile_contexts (user_id);
