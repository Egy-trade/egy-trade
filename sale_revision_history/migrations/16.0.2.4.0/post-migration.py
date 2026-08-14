# -*- coding: utf-8 -*-
"""Retire the daily-change gate and normalize proven revision families.

Historical customer references and issued PDFs are intentionally never renamed.
Only the internal family metadata is repaired.  The migration follows existing
``current_revision_id`` links and existing ``unrevisioned_name`` metadata; it
does not join separate quotations merely because their names look alike.
"""

import re


_SUFFIX_RE = re.compile(r"(?:-\d{2})+$")
_NUMBER_RE = re.compile(r"-(\d{2})$")


def _root(value, is_revision=False):
    value = (value or "").strip()
    return _SUFFIX_RE.sub("", value) if value and is_revision else value


def _number_from_name(name, root):
    if not name or not root or name == root or not name.startswith(root + "-"):
        return 0
    suffixes = name[len(root):].split("-")[1:]
    if not suffixes or not all(piece.isdigit() and len(piece) == 2 for piece in suffixes):
        return None
    return int(suffixes[-1])


def _mark_ambiguous(cr, ids, reason):
    cr.execute(
        """
        UPDATE sale_order
           SET revision_family_ambiguous = TRUE,
               revision_family_ambiguity_reason = %s
         WHERE id = ANY(%s)
        """,
        [reason, ids],
    )


def migrate(cr, version):
    # The obsolete wizard is no longer loaded.  Remove its old UI and access
    # records so existing databases cannot surface a stale daily-change popup.
    cr.execute(
        """
        DELETE FROM ir_ui_view
         WHERE id IN (
             SELECT res_id FROM ir_model_data
              WHERE module = 'sale_revision_history'
                AND name = 'quotation_commercial_change_view_form'
                AND model = 'ir.ui.view'
         )
        """
    )
    cr.execute(
        """
        DELETE FROM ir_model_access
         WHERE id IN (
             SELECT res_id FROM ir_model_data
              WHERE module = 'sale_revision_history'
                AND name = 'access_quotation_commercial_change_sales'
                AND model = 'ir.model.access'
         )
        """
    )
    cr.execute(
        """
        DELETE FROM ir_model_data
         WHERE module = 'sale_revision_history'
           AND name IN (
               'quotation_commercial_change_view_form',
               'access_quotation_commercial_change_sales'
           )
        """
    )

    cr.execute(
        """
        SELECT id, name, unrevisioned_name, revision_number, current_revision_id,
               company_id, partner_id, active
          FROM sale_order
        """
    )
    records = {
        row[0]: {
            "id": row[0], "name": row[1], "family": row[2],
            "number": row[3] or 0, "current": row[4],
            "company": row[5], "partner": row[6], "active": row[7],
        }
        for row in cr.fetchall()
    }

    def tip_for(record_id):
        current_id = record_id
        path = []
        seen = set()
        while records[current_id]["current"]:
            path.append(current_id)
            if current_id in seen:
                return None, path, "Existing revision links contain a circular reference; no automatic repair was made."
            seen.add(current_id)
            if records[current_id]["current"] not in records:
                return None, path, "Existing revision link points to a missing quotation; no automatic repair was made."
            current_id = records[current_id]["current"]
        path.append(current_id)
        return current_id, path, None

    groups = {}
    for record_id in records:
        tip, path, error = tip_for(record_id)
        if error:
            _mark_ambiguous(cr, path, error)
        else:
            groups.setdefault(tip, []).append(record_id)

    def write_verified_family(tip, members, root, numbers):
        # A family that was entirely archived remains entirely archived.  If
        # any linked member was visible, make only the proven newest member
        # visible so the main quotation list remains current-only.
        tip_active = any(member["active"] for member in members)
        for member, number in zip(members, numbers):
            cr.execute(
                """
                UPDATE sale_order
                   SET unrevisioned_name = %s,
                       revision_number = %s,
                       revision_family_ambiguous = FALSE,
                       revision_family_ambiguity_reason = NULL,
                       current_revision_id = CASE WHEN id = %s THEN NULL ELSE %s END,
                       active = CASE WHEN id = %s THEN %s ELSE FALSE END
                 WHERE id = %s
                """,
                [root, number, tip, tip, tip, tip_active, member["id"]],
            )

    for tip, ids in groups.items():
        members = [records[record_id] for record_id in ids]
        # The original revision-number-zero member is the strongest evidence
        # of a root.  Stored ``unrevisioned_name`` is otherwise trusted exactly
        # (a legitimate quotation root may itself end in '-01').
        roots = {
            (member["name"] or "").strip()
            for member in members if not member["number"]
        }
        roots.discard("")
        if len(roots) > 1:
            _mark_ambiguous(
                cr, ids,
                "Existing revision links identify more than one original quotation; no automatic merge was made.",
            )
            continue
        if not roots:
            roots = {
                (member["family"] or "").strip()
                for member in members if (member["family"] or "").strip()
            }
        if not roots:
            roots = {
                _root(member["name"], True)
                for member in members if member["number"]
            }
        if not roots and len(ids) > 1:
            # The explicit link proves a family.  A suffix in that linked
            # family is enough to repair a cumulative legacy name; otherwise
            # leave it for review instead of inventing a root.
            roots = {
                _root(member["name"], True)
                for member in members if _NUMBER_RE.search(member["name"] or "")
            }
        if not roots and len(ids) == 1:
            roots = {(members[0]["family"] or members[0]["name"] or "").strip()}

        roots.discard("")
        if len(roots) != 1:
            _mark_ambiguous(
                cr, ids,
                "Existing revision links/metadata identify more than one possible family root; no automatic merge was made.",
            )
            continue
        root = roots.pop()

        numbers = []
        conflict = False
        for member in members:
            parsed = _number_from_name(member["name"], root)
            if parsed is None:
                conflict = True
                break
            number = member["number"]
            if parsed and number and parsed != number:
                conflict = True
                break
            numbers.append(parsed or number)
        assigned = [number for number in numbers if number]
        if len(assigned) != len(set(assigned)):
            conflict = True
        if conflict:
            _mark_ambiguous(
                cr, ids,
                "Existing family metadata and quotation names disagree on revision numbering; no automatic renumbering was made.",
            )
            continue

        write_verified_family(tip, members, root, numbers)

    # Some older quotations were never linked by the legacy module.  Recover
    # only the narrow, auditable case: one un-suffixed root in the same company
    # and customer, plus one or more names that exactly use ``root-01`` or the
    # old cumulative ``root-01-02`` form.  Similar-looking quotations without a
    # unique root remain independent; they are never bundled by this migration.
    unlinked = [
        member for member in records.values()
        if not member["current"] and len(groups.get(member["id"], [])) == 1
    ]
    root_index = {}
    company_root_index = {}
    for member in unlinked:
        name = (member["name"] or "").strip()
        if member["number"] or not name or _NUMBER_RE.search(name):
            continue
        root_index.setdefault(
            (member["company"], member["partner"], name), []
        ).append(member)
        company_root_index.setdefault((member["company"], name), []).append(member)

    recovered = {}
    for member in unlinked:
        name = (member["name"] or "").strip()
        root = _root(name, True)
        if not name or root == name:
            continue
        candidates = root_index.get(
            (member["company"], member["partner"], root), []
        )
        if len(candidates) == 1:
            recovered.setdefault(candidates[0]["id"], []).append(member)
        elif len(candidates) > 1:
            _mark_ambiguous(
                cr, [candidate["id"] for candidate in candidates] + [member["id"]],
                "More than one unlinked root quotation matches this legacy revision name; no automatic bundle was made.",
            )
        else:
            same_company_roots = company_root_index.get((member["company"], root), [])
            if same_company_roots:
                _mark_ambiguous(
                    cr, [candidate["id"] for candidate in same_company_roots] + [member["id"]],
                    "The only matching unlinked root belongs to a different customer; no cross-customer bundle was made.",
                )
            elif member["number"]:
                _mark_ambiguous(
                    cr, [member["id"]],
                    "A revision-numbered unlinked quotation has no unique root quotation; no automatic bundle was made.",
                )

    for root_id, candidates in recovered.items():
        root_member = records[root_id]
        members = [root_member] + candidates
        parsed_numbers = [_number_from_name(member["name"], root_member["name"])
                          for member in members]
        conflict = any(number is None for number in parsed_numbers)
        for member, parsed in zip(members, parsed_numbers):
            if parsed and member["number"] and parsed != member["number"]:
                conflict = True
        assigned = [number for number in parsed_numbers if number]
        if len(assigned) != len(set(assigned)):
            conflict = True
        if conflict:
            _mark_ambiguous(
                cr, [member["id"] for member in members],
                "Unlinked legacy quotation names conflict on revision numbering; no automatic bundle was made.",
            )
            continue
        tip_index = max(range(len(members)), key=lambda index: parsed_numbers[index])
        tip = members[tip_index]["id"]
        write_verified_family(tip, members, root_member["name"], parsed_numbers)
