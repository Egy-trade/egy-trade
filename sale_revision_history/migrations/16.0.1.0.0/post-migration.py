# -*- coding: utf-8 -*-
"""Normalize historical snapshots created by the legacy revision module.

The legacy relation already points from each historical snapshot to the
then-current quotation.  That direction remains valid.  Legacy snapshots were
left active in the legacy ``cancel`` state, however, so archive those known
snapshots and backfill the structured metadata needed by the new filtered
history views. Confirmed or done orders are deliberately excluded even if bad
legacy data gave them a revision pointer; a migration must never hide them.
"""


def migrate(cr, version):
    cr.execute(
        """
        UPDATE sale_order
           SET active = FALSE,
               revision_date = CASE
                   WHEN NULLIF(revision_reason, '') IS NOT NULL
                   THEN COALESCE(revision_date, create_date)
                   ELSE revision_date
               END,
               revision_author_id = CASE
                   WHEN NULLIF(revision_reason, '') IS NOT NULL
                   THEN COALESCE(revision_author_id, create_uid)
                   ELSE revision_author_id
               END
         WHERE current_revision_id IS NOT NULL
           AND state = 'cancel'
        """
    )
