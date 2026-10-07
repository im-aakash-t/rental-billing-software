-- =====================================================================
-- Rental Billing - Supabase schema (run once in the SQL Editor)
--
-- Every business table mirrors the local SQLite table of the same name
-- and adds:  id uuid (global id), branch_id, updated_at (server time),
-- updated_by (device that made the change) and deleted (soft delete, so
-- branch PCs can learn about deletions when they sync).
-- Money columns are double precision on purpose: the local app stores
-- SQLite REAL (binary floating point) and the numbers must round-trip
-- exactly.
-- =====================================================================

create extension if not exists pgcrypto;

-- --------------------------------------------------------------- branches
create table if not exists public.branches (
  id          text primary key,              -- bill prefix: VDV / BMP / KVP
  name        text not null,
  is_main     boolean not null default false,
  created_at  timestamptz not null default now()
);

insert into public.branches (id, name, is_main) values
  ('VDV', 'Vadavalli', true),
  ('BMP', 'Bommanampalayam', false),
  ('KVP', 'Kalveerampalayam', false)
on conflict (id) do nothing;

-- --------------------------------------------------------------- user profiles
-- One row per login. A new sign-up has no branch/role and therefore sees
-- nothing until the owner assigns it (see admin_set_profile below).
create table if not exists public.profiles (
  user_id       uuid primary key references auth.users(id) on delete cascade,
  username      text unique not null,
  display_name  text,
  branch_id     text references public.branches(id),
  role          text check (role in ('owner', 'cashier')),
  active        boolean not null default false,
  created_at    timestamptz not null default now()
);

-- Create the (inactive) profile automatically when a user signs up.
create or replace function public.handle_new_user() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  insert into public.profiles (user_id, username, display_name)
  values (new.id,
          lower(split_part(new.email, '@', 1)),
          coalesce(new.raw_user_meta_data->>'display_name', split_part(new.email, '@', 1)))
  on conflict (user_id) do nothing;
  return new;
end $$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created after insert on auth.users
  for each row execute function public.handle_new_user();

-- --------------------------------------------------------------- access helpers
create or replace function public.is_owner() returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.profiles
                 where user_id = auth.uid() and role = 'owner' and active);
$$;

create or replace function public.my_branch() returns text
language sql stable security definer set search_path = public as $$
  select branch_id from public.profiles
  where user_id = auth.uid() and active and role in ('owner', 'cashier');
$$;

create or replace function public.can_access(b text) returns boolean
language sql stable security definer set search_path = public as $$
  select public.is_owner() or (b is not null and b = public.my_branch());
$$;

-- Owner-only: assign a login to a branch / role, or (de)activate it.
create or replace function public.admin_set_profile(
  p_user uuid, p_branch text, p_role text, p_active boolean, p_display_name text default null)
returns void language plpgsql security definer set search_path = public as $$
begin
  if not public.is_owner() then
    raise exception 'Only the owner can manage logins';
  end if;
  if p_user = auth.uid() and (p_role <> 'owner' or not p_active) then
    raise exception 'You cannot remove your own owner access';
  end if;
  update public.profiles
     set branch_id = p_branch, role = p_role, active = p_active,
         display_name = coalesce(p_display_name, display_name)
   where user_id = p_user;
end $$;

-- --------------------------------------------------------------- common trigger
create or replace function public.touch_row() returns trigger
language plpgsql as $$
begin
  new.updated_at := clock_timestamp();
  return new;
end $$;

-- --------------------------------------------------------------- business tables
create table if not exists public.rentals (
  id            uuid primary key default gen_random_uuid(),
  branch_id     text not null references public.branches(id),
  bill_no       text not null,
  name          text not null,
  phone         text not null,
  phone2        text,
  address       text,
  id_proof      text,
  machine_codes text,
  machines      text,
  rents         text,
  quantities    text,
  total         text,                       -- text on purpose: the app stores what was typed
  advance       text,                       -- (e.g. '500', '', '500A'); numbers round-trip exactly
  date          text not null,
  time          text not null,
  vehicle       text,
  payment_mode  text default 'Cash',
  adv_mode      text default 'Cash',
  cashier_name  text,
  cancelled     integer default 0,
  created_at    text,                       -- local creation timestamp (as text)
  updated_at    timestamptz not null default clock_timestamp(),
  updated_by    text,
  deleted       boolean not null default false,
  unique (branch_id, bill_no)
);

create table if not exists public.rental_items (
  id            uuid primary key default gen_random_uuid(),
  branch_id     text not null references public.branches(id),
  rental_id     uuid not null references public.rentals(id),
  machine_code  text,
  machine_name  text not null,
  quantity      integer not null,
  unit_price    double precision not null,
  total_price   double precision not null,
  updated_at    timestamptz not null default clock_timestamp(),
  updated_by    text,
  deleted       boolean not null default false
);

create table if not exists public.returns (
  id                  uuid primary key default gen_random_uuid(),
  branch_id           text not null references public.branches(id),
  rental_id           uuid not null references public.rentals(id),
  return_date         text not null,
  return_time         text not null,
  rental_days         integer not null,
  due_amount          double precision not null,
  deduction           double precision default 0,
  damage              double precision default 0,
  balance             double precision not null,
  amount_paid         double precision default 0,
  refund              double precision default 0,
  returned_items      text not null,
  returned_quantities text not null,
  payment_mode        text default 'Cash',
  paid_mode           text default 'Cash',
  cashier_name        text,
  created_at          text,
  updated_at          timestamptz not null default clock_timestamp(),
  updated_by          text,
  deleted             boolean not null default false,
  unique (rental_id)                      -- the app keeps one return record per bill
);

create table if not exists public.installments (
  id            uuid primary key default gen_random_uuid(),
  branch_id     text not null references public.branches(id),
  rental_id     uuid not null references public.rentals(id),
  amount        double precision not null,
  payment_mode  text default 'Cash',
  cashier_name  text,
  date_time     text not null,
  created_at    text,
  updated_at    timestamptz not null default clock_timestamp(),
  updated_by    text,
  deleted       boolean not null default false
);

create table if not exists public.refunds_history (
  id            uuid primary key default gen_random_uuid(),
  branch_id     text not null references public.branches(id),
  rental_id     uuid not null references public.rentals(id),
  amount        double precision not null,
  cashier_name  text,
  payment_mode  text default 'Cash',
  date_time     text not null,
  created_at    text,
  updated_at    timestamptz not null default clock_timestamp(),
  updated_by    text,
  deleted       boolean not null default false
);

create table if not exists public.customers (
  id            uuid primary key default gen_random_uuid(),
  branch_id     text not null references public.branches(id),
  name          text not null,
  phone         text not null,
  phone2        text,
  address       text,
  is_regular    integer default 0,
  updated_at    timestamptz not null default clock_timestamp(),
  updated_by    text,
  deleted       boolean not null default false,
  unique (branch_id, phone)
);

-- Each branch's machine list / prices / stock (uploaded from its materials.csv)
create table if not exists public.materials (
  id            uuid primary key default gen_random_uuid(),
  branch_id     text not null references public.branches(id),
  code          text not null,
  name          text not null,
  price         double precision not null,
  quantity      integer not null default 0,
  sort_order    integer not null default 0,
  updated_at    timestamptz not null default clock_timestamp(),
  updated_by    text,
  deleted       boolean not null default false,
  unique (branch_id, code)
);

-- ID proof photos: the file lives in Storage, this row links it to a bill
create table if not exists public.id_proofs (
  id            uuid primary key default gen_random_uuid(),
  branch_id     text not null references public.branches(id),
  bill_no       text not null,
  file_name     text not null,
  storage_path  text not null,
  updated_at    timestamptz not null default clock_timestamp(),
  updated_by    text,
  deleted       boolean not null default false,
  unique (branch_id, file_name)
);

-- When each branch PC last synced (so the owner can see who is offline)
create table if not exists public.sync_status (
  branch_id     text primary key references public.branches(id),
  device_id     text,
  last_sync_at  timestamptz,
  pending       integer default 0,
  app_version   text
);

-- --------------------------------------------------------------- indexes + triggers + RLS
do $$
declare t text;
begin
  foreach t in array array['rentals','rental_items','returns','installments','refunds_history',
                           'customers','materials','id_proofs'] loop
    execute format('create index if not exists %I on public.%I (branch_id, updated_at)', t || '_sync_idx', t);
    execute format('drop trigger if exists touch on public.%I', t);
    execute format('create trigger touch before insert or update on public.%I
                    for each row execute function public.touch_row()', t);
    execute format('alter table public.%I enable row level security', t);
    execute format('drop policy if exists branch_read on public.%I', t);
    execute format('drop policy if exists branch_insert on public.%I', t);
    execute format('drop policy if exists branch_update on public.%I', t);
    execute format('create policy branch_read on public.%I for select to authenticated
                    using (public.can_access(branch_id))', t);
    execute format('create policy branch_insert on public.%I for insert to authenticated
                    with check (public.can_access(branch_id))', t);
    execute format('create policy branch_update on public.%I for update to authenticated
                    using (public.can_access(branch_id)) with check (public.can_access(branch_id))', t);
    -- no delete policy: rows are only ever soft-deleted
  end loop;
end $$;

create index if not exists rental_items_rental_idx on public.rental_items (rental_id);
create index if not exists installments_rental_idx on public.installments (rental_id);
create index if not exists refunds_rental_idx on public.refunds_history (rental_id);

alter table public.branches enable row level security;
drop policy if exists branches_read on public.branches;
create policy branches_read on public.branches for select to authenticated using (true);

alter table public.profiles enable row level security;
drop policy if exists profiles_read on public.profiles;
create policy profiles_read on public.profiles for select to authenticated
  using (user_id = auth.uid() or public.is_owner());

alter table public.sync_status enable row level security;
drop policy if exists sync_status_read on public.sync_status;
drop policy if exists sync_status_write on public.sync_status;
drop policy if exists sync_status_update on public.sync_status;
create policy sync_status_read on public.sync_status for select to authenticated using (public.can_access(branch_id));
create policy sync_status_write on public.sync_status for insert to authenticated with check (public.can_access(branch_id));
create policy sync_status_update on public.sync_status for update to authenticated
  using (public.can_access(branch_id)) with check (public.can_access(branch_id));

-- --------------------------------------------------------------- storage: ID proof photos
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('id-proofs', 'id-proofs', false, 2097152, array['image/jpeg', 'image/png', 'image/webp'])
on conflict (id) do nothing;

-- objects are stored as  <branch_id>/<file name>
drop policy if exists id_proofs_read on storage.objects;
drop policy if exists id_proofs_insert on storage.objects;
drop policy if exists id_proofs_update on storage.objects;
create policy id_proofs_read on storage.objects for select to authenticated
  using (bucket_id = 'id-proofs' and public.can_access((storage.foldername(name))[1]));
create policy id_proofs_insert on storage.objects for insert to authenticated
  with check (bucket_id = 'id-proofs' and public.can_access((storage.foldername(name))[1]));
create policy id_proofs_update on storage.objects for update to authenticated
  using (bucket_id = 'id-proofs' and public.can_access((storage.foldername(name))[1]));

-- --------------------------------------------------------------- owner: reset a login's password
create or replace function public.admin_reset_password(p_user uuid, p_password text)
returns void language plpgsql security definer set search_path = public, extensions, auth as $$
begin
  if not public.is_owner() then
    raise exception 'Only the owner can reset passwords';
  end if;
  if length(coalesce(p_password, '')) < 6 then
    raise exception 'Password must be at least 6 characters';
  end if;
  update auth.users set encrypted_password = extensions.crypt(p_password, extensions.gen_salt('bf')),
                        updated_at = now()
   where id = p_user;
end $$;

revoke execute on function public.admin_reset_password(uuid, text) from public, anon;
revoke execute on function public.admin_set_profile(uuid, text, text, boolean, text) from public, anon;
grant execute on function public.admin_reset_password(uuid, text) to authenticated;
grant execute on function public.admin_set_profile(uuid, text, text, boolean, text) to authenticated;

-- --------------------------------------------------------------- table privileges
-- (Row-level security above decides WHICH rows; these decide which tables the
-- signed-in app may use at all. Nothing is granted to anonymous visitors.)
grant usage on schema public to authenticated;
grant select on public.branches, public.profiles to authenticated;
grant select, insert, update on public.rentals, public.rental_items, public.returns, public.installments,
  public.refunds_history, public.customers, public.materials, public.id_proofs, public.sync_status to authenticated;
revoke all on public.branches, public.profiles, public.rentals, public.rental_items, public.returns,
  public.installments, public.refunds_history, public.customers, public.materials, public.id_proofs,
  public.sync_status from anon;
grant execute on function public.is_owner(), public.my_branch(), public.can_access(text) to authenticated;

-- --------------------------------------------------------------- creation time for rows made on the phone/web
-- (same text format as SQLite's CURRENT_TIMESTAMP, which the branch PCs use)
do $$
declare t text;
begin
  foreach t in array array['rentals','returns','installments','refunds_history'] loop
    execute format($f$alter table public.%I alter column created_at
                     set default to_char(now() at time zone 'utc', 'YYYY-MM-DD HH24:MI:SS')$f$, t);
  end loop;
end $$;
