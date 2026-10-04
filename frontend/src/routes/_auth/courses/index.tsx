import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, getRouteApi, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { AuthPage } from "@/components/celestin/app-bar";
import { CourseCard } from "@/components/celestin/course-card";
import { CreateCourseForm } from "@/components/celestin/create-course-form";
import { primary } from "@/components/celestin/styles";
import { coursesQuery, createCourse, subjectsQuery } from "@/lib/tutor/courses";
import type { CourseLanguage } from "@/lib/course-language";
import type { SubjectId } from "@/lib/tutor/types";
import { m } from "@/paraglide/messages";

const authRoute = getRouteApi("/_auth");

export const Route = createFileRoute("/_auth/courses/")({
  head: () => ({ meta: [{ title: m.courses_head_title() }] }),
  loader: ({ context }) => context.queryClient.ensureQueryData(coursesQuery),
  component: CoursesPage,
});

function CoursesPage() {
  const { user } = authRoute.useRouteContext();
  const courses = useQuery(coursesQuery);
  const subjects = useQuery(subjectsQuery);
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [creating, setCreating] = useState(false);
  const create = useMutation({
    mutationFn: ({
      name,
      subject,
      language,
    }: {
      name: string;
      subject: SubjectId;
      language: CourseLanguage;
    }) => createCourse(name, subject, language),
    onSuccess: async (course) => {
      await queryClient.invalidateQueries({ queryKey: ["courses"] });
      await navigate({ to: "/courses/$courseId", params: { courseId: course.id } });
    },
  });
  const list = courses.data?.courses;
  return (
    <AuthPage user={user}>
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-bold">{m.nav_my_courses()}</h1>
        {!creating && (
          <button type="button" onClick={() => setCreating(true)} className={`${primary} ml-auto`}>
            {m.courses_new()}
          </button>
        )}
      </div>
      {courses.isError && !courses.data && (
        <p className="mt-3 text-sm text-destructive">{m.courses_load_failed()}</p>
      )}
      {creating && subjects.data && (
        <div className="mt-4">
          <CreateCourseForm
            subjects={subjects.data.subjects}
            onCreate={(name, subject, language) => create.mutateAsync({ name, subject, language })}
            onCancel={() => setCreating(false)}
          />
        </div>
      )}
      {list && list.length === 0 && !creating && (
        <p className="mt-4 text-sm text-muted-foreground">{m.courses_empty()}</p>
      )}
      {list && list.length > 0 && (
        <ul className="mt-4 grid gap-3 sm:grid-cols-2">
          {list.map((course) => (
            <li key={course.id}>
              <CourseCard course={course} />
            </li>
          ))}
        </ul>
      )}
    </AuthPage>
  );
}
