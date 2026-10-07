# cloud - multi-branch sync with Supabase.
#
# The billing logic keeps using the local SQLite database exactly as before
# (so the app works offline). SQLite triggers record every change into an
# outbox; the sync engine uploads it when online and downloads changes made
# for this branch from the phone/web app.
