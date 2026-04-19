-- PhD Europe App — Supabase schema
-- Run this once in the Supabase SQL Editor.

create table if not exists public.favorites (
  user_id     uuid        not null references auth.users(id) on delete cascade,
  job_url     text        not null,
  title       text,
  institution text,
  country     text,
  deadline    date,
  created_at  timestamptz not null default now(),
  primary key (user_id, job_url)
);

create index if not exists favorites_user_created_idx
  on public.favorites (user_id, created_at desc);

alter table public.favorites enable row level security;

drop policy if exists "select own favorites"  on public.favorites;
drop policy if exists "insert own favorites"  on public.favorites;
drop policy if exists "delete own favorites"  on public.favorites;

create policy "select own favorites"
  on public.favorites for select
  using (auth.uid() = user_id);

create policy "insert own favorites"
  on public.favorites for insert
  with check (auth.uid() = user_id);

create policy "delete own favorites"
  on public.favorites for delete
  using (auth.uid() = user_id);
