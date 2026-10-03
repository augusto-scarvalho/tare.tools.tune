// Just enough JSON to read a voice spec (Voice.to_json()): objects, arrays, numbers, strings, true/false/null.
#pragma once

#include <charconv>
#include <cstdint>
#include <cstdlib>
#include <stdexcept>
#include <string>
#include <string_view>
#include <tuple>
#include <utility>
#include <vector>

namespace tune {

struct Json {
    enum Kind { NUL, BOOL, NUM, STR, ARR, OBJ } kind = NUL;
    double num = 0.0;
    bool integer = false;    // written without a fraction or exponent: `whole` holds it exactly (seeds are 64-bit)
    uint64_t whole = 0;
    std::string str;
    std::vector<Json> arr;
    std::vector<std::pair<std::string, Json>> obj;

    const Json *get(std::string_view key) const {
        for (const auto &[k, v] : obj)
            if (k == key) return &v;
        return nullptr;
    }
    double number(std::string_view key, double fallback) const {
        const Json *v = get(key);
        return v && v->kind == NUM ? v->num : fallback;
    }
    std::string text(std::string_view key, const char *fallback) const {
        const Json *v = get(key);
        return v && v->kind == STR ? v->str : fallback;
    }
    const std::vector<Json> &list(std::string_view key) const {
        static const std::vector<Json> none;
        const Json *v = get(key);
        return v && v->kind == ARR ? v->arr : none;
    }

    Json *find(std::string_view key) {
        for (auto &[k, v] : obj)
            if (k == key) return &v;
        return nullptr;
    }
    void put(std::string_view key, Json value) {   // add or replace a field of an object
        if (Json *v = find(key))
            *v = std::move(value);
        else
            obj.emplace_back(std::string(key), std::move(value));
    }
    static Json of(double v) {
        Json j;
        j.kind = NUM;
        j.num = v;
        return j;
    }
    static Json of(const std::vector<double> &values) {
        Json j;
        j.kind = ARR;
        for (double v : values) j.arr.push_back(of(v));
        return j;
    }
    static Json of(const std::vector<std::vector<double>> &rows) {
        Json j;
        j.kind = ARR;
        for (const auto &r : rows) j.arr.push_back(of(r));
        return j;
    }

    static Json parse(std::string_view text) {
        std::size_t i = 0;
        Json out = value(text, i);
        skip(text, i);
        if (i != text.size()) throw std::runtime_error("trailing characters after the JSON value");
        return out;
    }

private:
    static void skip(std::string_view s, std::size_t &i) {
        while (i < s.size() && (s[i] == ' ' || s[i] == '\n' || s[i] == '\r' || s[i] == '\t')) ++i;
    }
    static void expect(std::string_view s, std::size_t &i, char c) {
        skip(s, i);
        if (i >= s.size() || s[i] != c) throw std::runtime_error(std::string("expected '") + c + "' in the JSON");
        ++i;
    }
    static void utf8(std::string &out, uint32_t c) {
        if (c < 0x80) {
            out += static_cast<char>(c);
        } else if (c < 0x800) {
            out += static_cast<char>(0xC0 | (c >> 6));
            out += static_cast<char>(0x80 | (c & 0x3F));
        } else {   // ponytail: a surrogate pair stays two code points; only informational text has them
            out += static_cast<char>(0xE0 | (c >> 12));
            out += static_cast<char>(0x80 | ((c >> 6) & 0x3F));
            out += static_cast<char>(0x80 | (c & 0x3F));
        }
    }
    static std::string string(std::string_view s, std::size_t &i) {
        expect(s, i, '"');
        std::string out;
        while (i < s.size() && s[i] != '"') {
            char c = s[i++];
            if (c != '\\') {
                out += c;
                continue;
            }
            if (i >= s.size()) break;
            switch (c = s[i++]) {
                case 'n': out += '\n'; break;
                case 't': out += '\t'; break;
                case 'r': out += '\r'; break;
                case 'b': out += '\b'; break;
                case 'f': out += '\f'; break;
                case 'u':
                    if (i + 4 > s.size()) throw std::runtime_error("bad \\u escape in the JSON");
                    utf8(out, static_cast<uint32_t>(std::strtoul(std::string(s.substr(i, 4)).c_str(), nullptr, 16)));
                    i += 4;
                    break;
                default: out += c;   // \" \\ \/
            }
        }
        if (i >= s.size()) throw std::runtime_error("unterminated string in the JSON");
        ++i;
        return out;
    }
    static Json value(std::string_view s, std::size_t &i) {
        skip(s, i);
        if (i >= s.size()) throw std::runtime_error("unexpected end of the JSON");
        Json v;
        const char c = s[i];
        if (c == '{') {
            v.kind = OBJ;
            ++i;
            skip(s, i);
            if (i < s.size() && s[i] == '}') return ++i, v;
            for (;;) {
                std::string k = string(s, i);
                expect(s, i, ':');
                v.obj.emplace_back(std::move(k), value(s, i));
                skip(s, i);
                if (i < s.size() && s[i] == ',') { ++i; continue; }
                expect(s, i, '}');
                return v;
            }
        }
        if (c == '[') {
            v.kind = ARR;
            ++i;
            skip(s, i);
            if (i < s.size() && s[i] == ']') return ++i, v;
            for (;;) {
                v.arr.push_back(value(s, i));
                skip(s, i);
                if (i < s.size() && s[i] == ',') { ++i; continue; }
                expect(s, i, ']');
                return v;
            }
        }
        if (c == '"') {
            v.kind = STR;
            v.str = string(s, i);
            return v;
        }
        static const std::tuple<const char *, Kind, bool> words[] = {{"true", BOOL, true}, {"false", BOOL, false},
                                                                     {"null", NUL, false}};
        for (const auto &[word, kind, flag] : words)
            if (s.substr(i, std::char_traits<char>::length(word)) == word) {
                i += std::char_traits<char>::length(word);
                v.kind = kind;
                v.num = flag;
                return v;
            }
        std::size_t end = i;
        while (end < s.size() && std::string_view("+-0123456789.eE").find(s[end]) != std::string_view::npos) ++end;
        if (end == i) throw std::runtime_error("unexpected character in the JSON");
        const char *first = s.data() + i, *last = s.data() + end;
        i = end;
        v.kind = NUM;
        // from_chars: correctly rounded (Python's repr floats come back exactly) and blind to the host's locale
        if (std::from_chars(first + (*first == '+'), last, v.num).ec != std::errc())
            throw std::runtime_error("bad number in the JSON");
        v.integer = std::string_view(first, last - first).find_first_of(".eE") == std::string_view::npos;
        if (v.integer && *first != '-') std::from_chars(first + (*first == '+'), last, v.whole);
        if (v.integer && *first == '-') {
            int64_t w = 0;
            std::from_chars(first, last, w);
            v.whole = static_cast<uint64_t>(w);
        }
        return v;
    }
};

}  // namespace tune
