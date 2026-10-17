-- Apply once to databases created before VirtualMachine.is_present existed.
ALTER TABLE virtual_machines
    ADD COLUMN IF NOT EXISTS is_present BOOLEAN NOT NULL DEFAULT TRUE;
