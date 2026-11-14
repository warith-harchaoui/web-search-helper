<?php
// web-search-helper — search endpoint. https://github.com/warith-harchaoui/web-search-helper
// BSD 3-Clause licence, Warith Harchaoui.
//
// Searches a corpus that the site never publishes. The page sends the question
// (and, once its in-browser model has computed it, the question's vector);
// this script ranks the passages and returns only short excerpts of those it
// retains, or nothing at all when the corpus does not treat the question.
//
// Twin of web_search_helper/engine.py: same tokenisation, same ranking, same
// verdict. tests/test_php_parity.py runs both on the same questions.
//
// Requirements: PHP >= 7.4 with mbstring. intl is used when present.
//
// POST JSON {"lang": "fr", "q": "...", "v": [384 floats]?}
//   -> {"sure": false, "terms": [...]}
//   -> {"sure": true, "terms": [...], "hits": [{doc, section, url, meta, text, o, cos, before, after}]}
// Errors: 400 bad request, 405 not POST, 429 too many requests, 500 index.
//
// Configuration: the index files live in WSH_DATA_DIR (default: ./search-data),
// one per language, named <lang>.php. Both can be set by defining the
// constants before including this file from a wrapper.

if (!defined('WSH_DATA_DIR')) define('WSH_DATA_DIR', __DIR__ . '/search-data');
if (!defined('WSH_STATE_DIR')) define('WSH_STATE_DIR', sys_get_temp_dir() . '/web-search-helper');
const WSH_HEADER = '<?php http_response_code(404); exit; __halt_compiler();';

// ------------------------------------------------------------ text --
// Twins of web_search_helper/text.py.

function wsh_fold($s) {
    $s = mb_strtolower($s, 'UTF-8');
    if (class_exists('Normalizer')) {
        $s = Normalizer::normalize($s, Normalizer::FORM_D);
        return preg_replace('/[\x{0300}-\x{036f}]/u', '', $s);
    }
    // Without intl: the Latin letters whose NFD decomposition is a base letter
    // followed by marks in U+0300–U+036F.
    static $table = null;
    if ($table === null) {
        $table = [];
        $groups = [
            'a' => 'àáâãäåāăąǎ', 'c' => 'çćĉċč', 'd' => 'ď', 'e' => 'èéêëēĕėęěȩ',
            'g' => 'ĝğġģǧ', 'h' => 'ĥȟ', 'i' => 'ìíîïĩīĭįǐ', 'j' => 'ĵǰ', 'k' => 'ķǩ',
            'l' => 'ĺļľ', 'n' => 'ñńņňǹ', 'o' => 'òóôõöōŏőơǒ', 'r' => 'ŕŗř',
            's' => 'śŝşšș', 't' => 'ţťț', 'u' => 'ùúûüũūŭůűųưǔ', 'w' => 'ŵ',
            'y' => 'ýÿŷ', 'z' => 'źżž',
        ];
        foreach ($groups as $base => $letters) {
            foreach (preg_split('//u', $letters, -1, PREG_SPLIT_NO_EMPTY) as $x) $table[$x] = $base;
        }
    }
    return strtr($s, $table);
}

function wsh_strip_math($s) {
    return preg_replace_callback('/\$\$([\s\S]+?)\$\$|\\\\\(([\s\S]+?)\\\\\)/u', function ($m) {
        $x = (isset($m[1]) && $m[1] !== '') ? $m[1] : (isset($m[2]) ? $m[2] : '');
        $x = preg_replace('/\\\\[a-zA-Z]+\s*/', '', $x);
        return preg_replace('/[{}\\\\]/', '', $x);
    }, $s);
}

function wsh_tokenize($s, $stop) {
    $out = [];
    foreach (preg_split('/[^\p{L}\p{N}]+/u', wsh_fold(wsh_strip_math($s)), -1, PREG_SPLIT_NO_EMPTY) as $w) {
        if (mb_strlen($w, 'UTF-8') > 2 && !isset($stop[$w])) $out[] = $w;
    }
    return $out;
}

function wsh_chars($s) { return preg_split('//u', $s, -1, PREG_SPLIT_NO_EMPTY); }

// ----------------------------------------------------------- index --

function wsh_load($path) {
    $raw = @file_get_contents($path);
    $h = strlen(WSH_HEADER);
    if ($raw === false || strncmp($raw, WSH_HEADER, $h) !== 0 || substr($raw, $h, 4) !== 'WSH1') return null;
    $o = $h + 4;
    $lm = unpack('V', $raw, $o)[1];
    $meta = json_decode(substr($raw, $o + 4, $lm), true);
    $o += 4 + $lm;
    $c = unpack('Vvec/Vsec/Vwords/Vblob', $raw, $o);
    $o += 16;
    $dim = $meta['dim'];
    $I = ['meta' => $meta, 'raw' => $raw, 'dim' => $dim, 'nsec' => $c['sec'], 'vecs' => $o];
    $o += $c['vec'] * $dim * 4;
    $I['cents'] = $o;
    $o += $c['sec'] * $dim * 4;
    $ll = unpack('V', $raw, $o)[1];
    $I['words'] = $ll ? explode("\n", substr($raw, $o + 4, $ll)) : [];
    $o += 4 + $ll;
    $I['offsets'] = $c['words'] ? array_values(unpack('V' . ($c['words'] + 1), $raw, $o)) : [0];
    $o += 4 * ($c['words'] + 1);
    $I['blob'] = $o;
    $o += $c['blob'];
    $n = count($meta['passages']);
    $I['lengths'] = $n ? array_values(unpack('V' . $n, $raw, $o)) : [];
    $I['idx'] = array_flip($I['words']);
    $I['stop'] = array_fill_keys($meta['stopwords'], true);
    $first = [];
    $cur = 0;
    foreach ($meta['passages'] as $i => $p) { $first[$i] = $cur; $cur += count($p['o']); }
    if ($cur !== $c['vec']) return null;
    $I['first'] = $first;
    return $I;
}

function wsh_vec(&$I, $base, $k) {
    return array_values(unpack('g' . $I['dim'], $I['raw'], $base + $k * $I['dim'] * 4));
}

function wsh_dot($a, $b, $dim) {
    $s = 0.0;
    for ($d = 0; $d < $dim; $d++) $s += $a[$d] * $b[$d];
    return $s;
}

function wsh_postings(&$I, $w) {
    if (!isset($I['idx'][$w])) return [];
    $k = $I['idx'][$w];
    $a = $I['offsets'][$k];
    $n = ($I['offsets'][$k + 1] - $a) / 6;
    $out = [];
    for ($j = 0; $j < $n; $j++) {
        $e = unpack('Vi/vtf', $I['raw'], $I['blob'] + $a + 6 * $j);
        $out[] = [$e['i'], $e['tf']];
    }
    return $out;
}

function wsh_df(&$I, $w) {
    $k = $I['idx'][$w];
    return ($I['offsets'][$k + 1] - $I['offsets'][$k]) / 6;
}

// ----------------------------------------------------------- words --

function wsh_max_typos($w) { $n = mb_strlen($w, 'UTF-8'); return $n < 4 ? 0 : ($n < 7 ? 1 : 2); }

function wsh_within($a, $b, $budget) {
    $a = wsh_chars($a);
    $b = wsh_chars($b);
    $la = count($a);
    $lb = count($b);
    if (abs($la - $lb) > $budget) return $budget + 1;
    $prev = range(0, $lb);
    for ($i = 1; $i <= $la; $i++) {
        $cur = [$i];
        $best = $i;
        for ($j = 1; $j <= $lb; $j++) {
            $cost = $a[$i - 1] === $b[$j - 1] ? 0 : 1;
            $cur[$j] = min($prev[$j] + 1, $cur[$j - 1] + 1, $prev[$j - 1] + $cost);
            if ($cur[$j] < $best) $best = $cur[$j];
        }
        if ($best > $budget) return $budget + 1;
        $prev = $cur;
    }
    return $prev[$lb];
}

function wsh_expand($qTerms, &$I) {
    $groups = [];
    $byLen = null;
    foreach ($qTerms as $t) {
        if (isset($I['idx'][$t])) { $groups[] = [[$t, 1.0]]; continue; }
        $budget = wsh_max_typos($t);
        $cands = [];
        if ($budget) {
            if ($byLen === null) {
                $byLen = [];
                foreach ($I['words'] as $w) $byLen[mb_strlen($w, 'UTF-8')][] = $w;
            }
            $n = mb_strlen($t, 'UTF-8');
            for ($len = $n - $budget; $len <= $n + $budget; $len++) {
                if (empty($byLen[$len])) continue;
                foreach ($byLen[$len] as $w) {
                    $w = (string)$w;
                    $d = wsh_within($t, $w, $budget);
                    if ($d <= $budget) $cands[] = [$w, $d, wsh_df($I, $w) / ((1 + $d) * (1 + $d))];
                }
            }
        }
        if (!$cands) { $groups[] = []; continue; }
        usort($cands, function ($x, $y) { return $y[2] <=> $x[2]; });
        $floor = $cands[0][2] / 4;
        $kept = [];
        foreach ($cands as $c) {
            if ($c[2] >= $floor && count($kept) < 3) $kept[] = [$c[0], 1 / (1 + $c[1])];
        }
        $groups[] = $kept;
    }
    return $groups;
}

function wsh_lexical($q, &$I) {
    $qTerms = array_values(array_unique(wsh_tokenize($q, $I['stop'])));
    $typed = count(preg_split('/\s+/u', $q, -1, PREG_SPLIT_NO_EMPTY));
    $poolK = $I['meta']['ranking']['pool_k'];
    if (!$qTerms) return ['ranked' => [], 'terms' => [], 'best' => 0.0, 'conj' => false, 'df1' => 0, 'typed' => $typed];
    $groups = wsh_expand($qTerms, $I);
    $G = count($groups);
    $N = count($I['meta']['passages']);
    $tf = [];
    $cands = [];
    foreach ($groups as $gi => $g) {
        foreach ($g as $var) {
            foreach (wsh_postings($I, $var[0]) as $e) {
                $i = $e[0];
                if (!isset($tf[$i])) { $tf[$i] = array_fill(0, $G, 0.0); $cands[] = $i; }
                $tf[$i][$gi] += $e[1] * $var[1];
            }
        }
    }
    $df = array_fill(0, $G, 0);
    foreach ($cands as $i) for ($gi = 0; $gi < $G; $gi++) if ($tf[$i][$gi]) $df[$gi]++;
    $idf = [];
    foreach ($df as $gi => $d) $idf[$gi] = log(1 + ($N - $d + 0.5) / ($d + 0.5));
    $k1 = 1.5;
    $b = 0.75;
    $avg = $I['meta']['avg_len'];
    $conj = [];
    $union = [];
    foreach ($cands as $i) {
        $s = 0.0;
        $matched = 0;
        for ($gi = 0; $gi < $G; $gi++) {
            $x = $tf[$i][$gi];
            if (!$x) continue;
            $matched++;
            $s += $idf[$gi] * ($x * ($k1 + 1)) / ($x + $k1 * (1 - $b + $b * $I['lengths'][$i] / $avg));
        }
        $cov = $matched / $G;
        if ($matched === $G) $conj[] = [$s * $cov * $cov, $i]; else $union[] = [$s * $cov * $cov, $i];
    }
    $pool = $conj ? $conj : $union;
    usort($pool, function ($x, $y) { return ($y[0] <=> $x[0]) ?: ($x[1] <=> $y[1]); });
    $terms = [];
    foreach ($groups as $g) foreach ($g as $var) $terms[] = $var[0];
    $ranked = [];
    foreach (array_slice($pool, 0, $poolK) as $e) $ranked[] = $e[1];
    return ['ranked' => $ranked, 'terms' => $terms, 'best' => $pool ? $pool[0][0] : 0.0,
            'conj' => count($conj) > 0, 'df1' => $G === 1 ? $df[0] : 0, 'typed' => $typed];
}

// --------------------------------------------------------- meaning --

// The cosine of every window with the question. This loop is the whole cost of
// a request: n_windows × dim multiply-adds. It decodes the vectors by blocks
// of 256 windows (one unpack each, about 0.4 MB) rather than one window at a
// time, which was three times slower, and rather than all at once, which
// costs about 15 bytes of PHP memory per float (90 MB for 6 000 windows).
function wsh_window_dots($qv, &$I) {
    $dim = $I['dim'];
    $n = $I['cents'] - $I['vecs'];
    $n = intdiv($n, 4 * $dim);
    $dots = [];
    $block = 256;
    for ($w0 = 0; $w0 < $n; $w0 += $block) {
        $nb = min($block, $n - $w0);
        $x = unpack('g' . ($nb * $dim), $I['raw'], $I['vecs'] + $w0 * $dim * 4);
        $k = 1;
        for ($w = 0; $w < $nb; $w++) {
            $s = 0.0;
            for ($d = 0; $d < $dim; $d++) $s += $qv[$d] * $x[$k++];
            $dots[] = $s;
        }
    }
    return $dots;
}

function wsh_semantic($qv, &$I) {
    $dim = $I['dim'];
    $dots = wsh_window_dots($qv, $I);
    $I['dots'] = $dots;
    $best = [];
    foreach ($I['meta']['passages'] as $i => $p) {
        $m = -INF;
        $a = $I['first'][$i];
        $nf = count($p['o']);
        for ($f = 0; $f < $nf; $f++) if ($dots[$a + $f] > $m) $m = $dots[$a + $f];
        $best[$i] = $m;
    }
    $order = array_keys($best);
    usort($order, function ($x, $y) use ($best) { return $best[$y] <=> $best[$x]; });
    $sectop = -1.0;
    for ($s = 0; $s < $I['nsec']; $s++) {
        $d = wsh_dot($qv, wsh_vec($I, $I['cents'], $s), $dim);
        if ($s === 0 || $d > $sectop) $sectop = $d;
    }
    return ['ranked' => array_slice($order, 0, $I['meta']['ranking']['pool_k']),
            'top' => $order ? $best[$order[0]] : 0.0, 'sectop' => $sectop, 'best' => $best];
}

function wsh_sure($kw, $sem, $th) {
    if (!$kw['terms']) return false;
    if ($kw['typed'] === 1) return $kw['df1'] >= $th['df_min'];
    if ($sem !== null && $sem['top'] >= $th['sem_min'] && $sem['sectop'] >= $th['sec_min']) return true;
    return $kw['conj'] && $kw['best'] >= $th['lex_min'];
}

function wsh_rrf($a, $b, $k, $top) {
    $scores = [];
    foreach ([$a, $b] as $ranking) {
        foreach ($ranking as $r => $i) $scores[$i] = (isset($scores[$i]) ? $scores[$i] : 0.0) + 1 / ($k + $r + 1);
    }
    $ids = array_keys($scores);
    usort($ids, function ($x, $y) use ($scores) { return $scores[$y] <=> $scores[$x]; });
    return array_slice($ids, 0, $top);
}

// -------------------------------------------------------- excerpts --

function wsh_starts_upper($s) { return preg_match('/^[«"“(]*[\p{Lu}\p{Lt}0-9]/u', $s) === 1; }

// TeX formulas an excerpt must never cut: display $$…$$ and \[…\], inline \(…\).
// Spans in characters, like the window offsets.
function wsh_math_spans($t) {
    $spans = [];
    if (preg_match_all('/\$\$.*?\$\$|\\\\\[.*?\\\\\]|\\\\\(.*?\\\\\)/su', $t, $mm, PREG_OFFSET_CAPTURE)) {
        foreach ($mm[0] as $hit) {
            $a = mb_strlen(substr($t, 0, $hit[1]), 'UTF-8');
            $spans[] = [$a, $a + mb_strlen($hit[0], 'UTF-8')];
        }
    }
    return $spans;
}

// A bound inside a formula moves out of it, the start back to its opening, the
// end on past its closing, so the page never receives half a formula.
function wsh_outside_math($spans, &$start, &$end) {
    foreach ($spans as $s) {
        if ($s[0] < $start && $start < $s[1]) $start = $s[0];
        if ($s[0] < $end && $end < $s[1]) $end = $s[1];
    }
}

function wsh_excerpt($i, $qv, $terms, &$I) {
    $p = $I['meta']['passages'][$i];
    $t = $p['t'];
    $o = $p['o'];
    $n = mb_strlen($t, 'UTF-8');
    $nf = count($o);
    $note = [];
    if ($qv !== null) {
        for ($f = 0; $f < $nf; $f++) {
            $note[] = isset($I['dots']) ? $I['dots'][$I['first'][$i] + $f]
                                        : wsh_dot($qv, wsh_vec($I, $I['vecs'], $I['first'][$i] + $f), $I['dim']);
        }
    } else {
        $tset = array_fill_keys($terms, true);
        for ($f = 0; $f < $nf; $f++) {
            $a = $f ? $o[$f - 1] : 0;
            $c = 0;
            foreach (wsh_tokenize(mb_substr($t, $a, $o[$f] - $a, 'UTF-8'), []) as $w) if (isset($tset[$w])) $c++;
            $note[] = (float)$c;
        }
    }
    $m = array_search(max($note), $note, true);
    $lo = $m;
    $hi = $m;
    if ($nf > 1) {
        if ($m === 0) $hi = 1;
        elseif ($m === $nf - 1) $lo = $m - 1;
        elseif ($note[$m - 1] > $note[$m + 1]) $lo = $m - 1;
        else $hi = $m + 1;
    }
    $start = $lo ? $o[$lo - 1] : 0;
    $end = $o[$hi];
    $spans = wsh_math_spans($t);
    wsh_outside_math($spans, $start, $end);
    if ($start > 0) {
        $chunk = mb_substr($t, $start, $end - $start, 'UTF-8');
        if (preg_match_all('/[.!?…]\s+/u', $chunk, $mm, PREG_OFFSET_CAPTURE)) {
            foreach ($mm[0] as $hit) {
                $after = $hit[1] + strlen($hit[0]);
                if (wsh_starts_upper(substr($chunk, $after))) {
                    $adv = mb_strlen(substr($chunk, 0, $after), 'UTF-8');
                    if ($adv < $end - $start) $start += $adv;
                    break;
                }
            }
        }
    }
    if ($end < $n) {
        $tail = mb_substr($t, $end, 400, 'UTF-8');
        if (preg_match_all('/[.!?…]/u', $tail, $mm, PREG_OFFSET_CAPTURE)) {
            foreach ($mm[0] as $hit) {
                $after = $hit[1] + strlen($hit[0]);
                $rest = substr($tail, $after);
                if (trim($rest) === '' || (preg_match('/^\s/u', $rest) && wsh_starts_upper(ltrim($rest)))) {
                    $end += mb_strlen(substr($tail, 0, $after), 'UTF-8');
                    break;
                }
            }
        }
    }
    wsh_outside_math($spans, $start, $end);
    $bounds = [];
    $cos = [];
    for ($f = $lo; $f <= $hi; $f++) {
        $bounds[] = max(0, min($o[$f], $end) - $start);
        $cos[] = $qv !== null ? $note[$f] : 0.0;
    }
    $bounds[count($bounds) - 1] = $end - $start;
    return [
        'doc' => $p['c'], 'section' => $p['s'],
        'url' => isset($p['u']) ? $p['u'] : '', 'meta' => isset($p['m']) ? $p['m'] : new stdClass(),
        'text' => mb_substr($t, $start, $end - $start, 'UTF-8'),
        'o' => $bounds, 'cos' => $cos, 'before' => $start > 0, 'after' => $end < $n,
    ];
}

function wsh_search(&$I, $q, $qv) {
    $q = trim($q);
    $kw = wsh_lexical($q, $I);
    $sem = $qv !== null ? wsh_semantic($qv, $I) : null;
    $sure = wsh_sure($kw, $sem, $I['meta']['thresholds']);
    $out = ['sure' => $sure, 'terms' => $kw['terms']];
    if (!$sure) return $out;
    $r = $I['meta']['ranking'];
    $keep = $sem ? wsh_rrf($kw['ranked'], $sem['ranked'], $r['rrf_k'], $r['answer_pool'])
                 : array_slice($kw['ranked'], 0, $r['display_k']);
    $out['hits'] = [];
    foreach ($keep as $i) $out['hits'][] = wsh_excerpt($i, $qv, $kw['terms'], $I);
    return $out;
}

// ----------------------------------------------------------- quota --
// Only a salted hash of the address and the times of its calls of the last
// day are kept; nothing else.
function wsh_quota($limits) {
    $dir = WSH_STATE_DIR;
    if (!is_dir($dir) && !@mkdir($dir, 0700, true) && !is_dir($dir)) return true;
    $saltFile = $dir . '/salt';
    $salt = @file_get_contents($saltFile);
    if (!$salt) {
        $salt = bin2hex(random_bytes(16));
        @file_put_contents($saltFile, $salt, LOCK_EX);
    }
    $ip = isset($_SERVER['REMOTE_ADDR']) ? $_SERVER['REMOTE_ADDR'] : '';
    $f = @fopen($dir . '/' . hash('sha256', $salt . $ip), 'c+');
    if (!$f) return true;
    flock($f, LOCK_EX);
    $now = time();
    $calls = [];
    foreach (explode("\n", stream_get_contents($f)) as $t) {
        if ($t !== '' && (int)$t > $now - 86400) $calls[] = (int)$t;
    }
    $hour = 0;
    foreach ($calls as $t) if ($t > $now - 3600) $hour++;
    $ok = $hour < $limits['per_hour'] && count($calls) < $limits['per_day'];
    if ($ok) $calls[] = $now;
    ftruncate($f, 0);
    rewind($f);
    fwrite($f, implode("\n", $calls));
    flock($f, LOCK_UN);
    fclose($f);
    return $ok;
}

// ------------------------------------------------------------ HTTP --

function wsh_reply($code, $body) {
    http_response_code($code);
    echo json_encode($body, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_PRESERVE_ZERO_FRACTION);
    exit;
}

function wsh_main() {
    header('Content-Type: application/json; charset=utf-8');
    header('Cache-Control: no-store');
    header('X-Robots-Tag: noindex');
    if ($_SERVER['REQUEST_METHOD'] !== 'POST') wsh_reply(405, ['error' => 'POST only']);
    $in = json_decode(file_get_contents('php://input'), true);
    if (!is_array($in)) wsh_reply(400, ['error' => 'JSON body expected']);
    $lang = isset($in['lang']) && is_string($in['lang']) ? $in['lang'] : '';
    if (!preg_match('/^[a-z]{2,3}(-[a-z0-9]{2,8})?$/', $lang)) wsh_reply(400, ['error' => 'lang']);
    $I = wsh_load(WSH_DATA_DIR . '/' . $lang . '.php');
    if ($I === null) wsh_reply(404, ['error' => 'no index for this language']);
    $q = isset($in['q']) && is_string($in['q']) ? trim($in['q']) : '';
    if ($q === '' || mb_strlen($q, 'UTF-8') > $I['meta']['limits']['q_max']) wsh_reply(400, ['error' => 'q']);
    $qv = null;
    if (isset($in['v'])) {
        $v = $in['v'];
        if (!is_array($v) || count($v) !== $I['dim']) wsh_reply(400, ['error' => 'v']);
        $n2 = 0.0;
        $qv = [];
        foreach ($v as $x) {
            if (!is_int($x) && !is_float($x)) wsh_reply(400, ['error' => 'v']);
            $qv[] = (float)$x;
            $n2 += $x * $x;
        }
        // Renormalised, so that a hand-made vector cannot push cosines past 1.
        if ($n2 <= 0) wsh_reply(400, ['error' => 'v']);
        $inv = 1 / sqrt($n2);
        foreach ($qv as $d => $x) $qv[$d] = $x * $inv;
    }
    if (!wsh_quota($I['meta']['limits'])) wsh_reply(429, ['error' => 'too many requests']);
    wsh_reply(200, wsh_search($I, $q, $qv));
}

// Included by a test harness or a wrapper that defines WSH_NO_MAIN: only the
// functions are loaded.
if (!defined('WSH_NO_MAIN') && PHP_SAPI !== 'cli') wsh_main();
