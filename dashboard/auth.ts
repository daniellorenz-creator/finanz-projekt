import NextAuth from 'next-auth'
import GitHub from 'next-auth/providers/github'

export const { handlers, auth, signIn, signOut } = NextAuth({
  providers: [
    GitHub({
      clientId: process.env.GITHUB_ID,
      clientSecret: process.env.GITHUB_SECRET,
    }),
  ],
  session: {
    maxAge: 8 * 60 * 60, // 8 Stunden
  },
  callbacks: {
    signIn({ profile }) {
      return profile?.login === process.env.GITHUB_ALLOWED_USER
    },
  },
})
