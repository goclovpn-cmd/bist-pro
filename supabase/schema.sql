-- 1. Portföy verileri tablosu
create table if not exists public.portfolios (
  user_id uuid primary key references auth.users(id) on delete cascade,
  data jsonb not null,
  updated_at timestamptz default now()
);

-- 2. Kötü niyetli veri şişirmesine (payload spam) karşı kullanıcı başı 250 KB sınırı
alter table public.portfolios
  drop constraint if exists max_portfolio_size;
alter table public.portfolios
  add constraint max_portfolio_size
  check (pg_column_size(data) <= 262144);

-- 3. Row Level Security (RLS) - Her kullanıcı yalnızca kendi verisini yönetir
alter table public.portfolios enable row level security;

drop policy if exists "Kullanici kendi portfoyunu yonetir" on public.portfolios;
create policy "Kullanici kendi portfoyunu yonetir"
  on public.portfolios for all
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

-- 4. Davet kodları tablosu (isteğe bağlı erişim kontrolü)
create table if not exists public.davet_kodlari (
  kod text primary key,
  aktif boolean not null default true,
  kullanim_sayisi int not null default 0,
  max_kullanim int not null default 50
);

alter table public.davet_kodlari enable row level security;

-- Varsayılan ilk davet kodu (kendi belirleyeceğiniz kodla değiştirin)
insert into public.davet_kodlari (kod, aktif, max_kullanim)
values ('DODNI2026', true, 50)
on conflict (kod) do nothing;

-- 5. Yeni kayıt anında davet kodunu doğrulayan veritabanı tetikleyicisi
create or replace function public.davet_kodu_kontrol()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  girilen_kod text;
begin
  girilen_kod := upper(trim(coalesce(new.raw_user_meta_data->>'invite_code', '')));

  if girilen_kod = '' then
    raise exception 'Kayit icin davet kodu gereklidir.';
  end if;

  update public.davet_kodlari
  set kullanim_sayisi = kullanim_sayisi + 1
  where kod = girilen_kod
    and aktif = true
    and kullanim_sayisi < max_kullanim;

  if not found then
    raise exception 'Gecersiz veya kullanim limiti dolmus davet kodu.';
  end if;

  return new;
end;
$$;

drop trigger if exists trg_davet_kodu_kontrol on auth.users;
create trigger trg_davet_kodu_kontrol
  before insert on auth.users
  for each row execute function public.davet_kodu_kontrol();
